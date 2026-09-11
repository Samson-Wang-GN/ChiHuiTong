import math
import re
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from chihuitong.crypto import normalize_phone
from chihuitong.errors import BusinessError, require
from chihuitong.models import (
    Clinic,
    ClinicProduct,
    ClinicProfileChange,
    Membership,
    Organization,
    Product,
)

from .common import advance, audit, check_version
from .contracts import current_contract, workday_due

PROFILE_KEYS = {
    "name",
    "legal_entity",
    "province",
    "city",
    "district",
    "address",
    "business_hours",
    "frontdesk_phone",
    "business_contact",
    "business_phone",
    "cover_id",
    "business_license_ids",
    "medical_license_ids",
    "location",
    "responsible_id",
}


def visible_clinics(actor):
    qs = Clinic.objects.select_related("organization", "channel", "responsible")
    if actor.platform:
        return qs
    if actor.organization.kind == "channel":
        qs = qs.filter(channel=actor.organization)
        if actor.membership.role != "admin":
            qs = qs.filter(responsible=actor.membership)
        return qs
    if actor.organization.kind == "clinic":
        return qs.filter(organization=actor.organization)
    return qs.none()


def get_clinic(actor, clinic_id, *, lock=False, edit=False):
    qs = visible_clinics(actor)
    if lock:
        qs = qs.select_for_update(of=("self",))
    clinic = qs.filter(pk=clinic_id).first()
    require(clinic, "not_found", "门诊不存在或无权访问", 404)
    if edit and actor.organization.kind == "clinic":
        actor.require_admin()
    return clinic


def normalize_business_phone(phone):
    require(isinstance(phone, str), "invalid_contact_phone", "联系人电话不合法", 400)
    cleaned = re.sub(r"[\s()]", "", phone.strip())
    if re.fullmatch(r"0\d{2,3}-?\d{7,8}", cleaned):
        return cleaned
    return normalize_phone(phone)


def validate_profile(actor, profile, channel, *, complete=True):
    require(
        isinstance(profile, dict) and not (set(profile) - PROFILE_KEYS),
        "invalid_fields",
        "门诊资料包含不允许修改的字段",
        400,
    )
    value = dict(profile)
    required = {
        "name",
        "legal_entity",
        "province",
        "city",
        "district",
        "address",
        "business_hours",
        "frontdesk_phone",
        "business_contact",
        "business_phone",
    }
    for key in required:
        if key in value:
            require(
                isinstance(value[key], str) and len(value[key]) <= 500,
                "invalid_profile",
                "门诊资料字段不合法",
                400,
            )
            value[key] = value[key].strip()
        if complete:
            require(
                bool(value.get(key)),
                "incomplete_profile",
                "请补齐名称、主体、地址、营业时间及两类联系人信息",
                400,
            )
    if value.get("frontdesk_phone"):
        value["frontdesk_phone"] = normalize_phone(value["frontdesk_phone"])
    if value.get("business_phone"):
        value["business_phone"] = normalize_business_phone(value["business_phone"])
    from .files import validate_attachment_ids

    for key in ["business_license_ids", "medical_license_ids"]:
        if complete or value.get(key):
            validate_attachment_ids(actor, value.get(key, []), purposes={"license"})
    if value.get("cover_id"):
        validate_attachment_ids(actor, [value["cover_id"]], purposes={"cover"})
    responsible = Membership.objects.filter(
        pk=value.get("responsible_id"), organization=channel, active=True, account__active=True
    ).first()
    require(responsible, "responsible_required", "请选择本渠道有效的负责业务员", 400)
    location = value.get("location") or {"status": "unconfirmed"}
    if isinstance(location, dict):
        location = {k: v for k, v in location.items() if k not in {"confirmed_by", "confirmed_at"}}
    require(
        isinstance(location, dict)
        and not (
            set(location)
            - {
                "status",
                "longitude",
                "latitude",
                "coordinate_system",
                "address_snapshot",
                "source",
                "confirmed",
                "precision",
            }
        ),
        "invalid_location",
        "定位字段不合法",
        400,
    )
    if location.get("status") == "confirmed":
        try:
            lng, lat = (
                Decimal(str(location.get("longitude"))),
                Decimal(str(location.get("latitude"))),
            )
            require(
                lng.is_finite()
                and lat.is_finite()
                and -180 <= lng <= 180
                and -90 <= lat <= 90
                and (lng != 0 or lat != 0),
                "invalid_location",
                "经纬度不合法",
                400,
            )
        except (InvalidOperation, ValueError) as exc:
            raise BusinessError("invalid_location", "经纬度不合法", 400) from exc
        address = "".join(value.get(key, "") for key in ("province", "city", "district", "address"))
        require(
            location.get("coordinate_system") == "GCJ-02"
            and location.get("address_snapshot") == address
            and location.get("confirmed") is True,
            "location_unconfirmed",
            "请在地图核对当前地址的位置后确认",
            400,
        )
        require(
            location.get("source") in {"map_manual", "tencent"},
            "invalid_location",
            "定位来源不合法",
            400,
        )
        location = dict(
            location,
            longitude=str(lng),
            latitude=str(lat),
            confirmed_by=str(actor.membership.id),
            confirmed_at=timezone.now().isoformat(),
        )
    else:
        require(
            location.get("status") in {"unconfirmed", None},
            "invalid_location",
            "定位状态不合法",
            400,
        )
        location = {"status": "unconfirmed"}
    value["location"] = location
    return value, responsible


def profile_attachment_ids(profile):
    return (
        profile.get("business_license_ids", [])
        + profile.get("medical_license_ids", [])
        + ([profile["cover_id"]] if profile.get("cover_id") else [])
    )


@transaction.atomic
def create_clinic(actor, *, channel_id, profile, admin_name, admin_phone):
    require(
        actor.platform or actor.organization.kind == "channel",
        "forbidden",
        "只有平台或渠道可以录入门诊",
        403,
    )
    channel = Organization.objects.filter(pk=channel_id, kind="channel", status="active").first()
    require(
        channel and (actor.platform or channel.id == actor.organization.id),
        "not_found",
        "渠道不存在或无权访问",
        404,
    )
    current_contract(channel.id)
    normalized, responsible = validate_profile(actor, profile, channel, complete=False)
    if not actor.platform and actor.membership.role != "admin":
        require(
            responsible.id == actor.membership.id, "forbidden", "业务员只能录入本人负责的门诊", 403
        )
    org = Organization.objects.create(name=normalized.get("name") or "待完善门诊", kind="clinic")
    clinic = Clinic.objects.create(
        organization=org, channel=channel, responsible=responsible, profile=normalized
    )
    from .organizations import account_for

    account = account_for(admin_phone, admin_name)
    Membership.objects.create(
        organization=org, account=account, role="admin", platform_created=actor.platform
    )
    audit(actor, clinic, "clinic.created")
    return clinic


@transaction.atomic
def submit_profile(actor, clinic_id, *, profile, version):
    clinic = get_clinic(actor, clinic_id, lock=True, edit=True)
    check_version(clinic, version)
    require(
        not clinic.profile_changes.filter(status="pending").exists(),
        "pending_profile",
        "已有待审核资料，请等待平台处理",
    )
    normalized, _ = validate_profile(actor, profile, clinic.channel)
    if actor.organization.kind == "clinic":
        require(
            str(normalized["responsible_id"]) == str(clinic.responsible_id),
            "forbidden",
            "门诊不能变更渠道负责业务员",
            403,
        )
    current = dict(clinic.profile)
    # Allow callers to reuse approved location metadata, but never to forge the audit metadata.
    if clinic.profile_version > 0:
        def comparable(profile):
            return {
                **profile,
                "location": {
                    k: v
                    for k, v in profile.get("location", {}).items()
                    if k not in {"confirmed_by", "confirmed_at"}
                },
            }
        require(comparable(current) != comparable(normalized), "unchanged_profile", "资料没有变更")
    change = ClinicProfileChange.objects.create(
        clinic=clinic,
        base_version=clinic.profile_version,
        before=current,
        after=normalized,
        submitted_by=actor.membership,
        due_at=workday_due(timezone.now()),
    )
    from .files import link_files

    link_files(profile_attachment_ids(normalized), clinic)
    if clinic.profile_version == 0:
        clinic.review_status = "pending"
        advance(clinic, "review_status")
    else:
        advance(clinic)
    audit(
        actor,
        clinic,
        "clinic.profile_submitted",
        change_id=str(change.id),
        base_version=clinic.profile_version,
    )
    return change


@transaction.atomic
def review_profile(actor, change_id, *, approved, version, reason):
    actor.require_platform()
    pending = ClinicProfileChange.objects.filter(pk=change_id).first()
    require(pending, "not_found", "资料申请不存在", 404)
    clinic = Clinic.objects.select_for_update().get(pk=pending.clinic_id)
    change = ClinicProfileChange.objects.select_for_update().get(pk=change_id)
    check_version(change, version)
    require(change.status == "pending", "invalid_state", "申请已处理")
    require(
        change.base_version == clinic.profile_version,
        "stale_version",
        "生效资料版本已变化，请重新提交",
    )
    require(
        isinstance(approved, bool) and reason.strip(),
        "reason_required",
        "请填写审核结论及意见",
        400,
    )
    if approved:
        data = dict(change.after)
        if data.get("location"):
            data["location"] = {
                k: v
                for k, v in data["location"].items()
                if k not in {"confirmed_by", "confirmed_at"}
            }
        _, responsible = validate_profile(actor, data, clinic.channel)
        clinic.profile = change.after
        clinic.profile_version += 1
        clinic.responsible = responsible
        clinic.review_status = "approved"
        clinic.organization.name = change.after["name"]
        clinic.organization.save(update_fields=["name", "updated_at"])
        advance(clinic, "profile", "profile_version", "responsible", "review_status")
    elif clinic.profile_version == 0:
        clinic.review_status = "rejected"
        advance(clinic, "review_status")
    change.status, change.reason = ("approved" if approved else "rejected"), reason
    change.reviewed_by, change.reviewed_at = actor.membership, timezone.now()
    advance(change, "status", "reason", "reviewed_by", "reviewed_at")
    audit(
        actor,
        clinic,
        "clinic.profile_reviewed",
        reason=reason,
        change_id=str(change.id),
        status=change.status,
    )
    return change


def assert_new_business(clinic, product_id=None):
    require(
        clinic.organization.status == "active" and clinic.channel.status == "active",
        "organization_disabled",
        "机构已停用，暂不能新增预约",
    )
    require(
        clinic.review_status == "approved" and clinic.profile_version > 0,
        "clinic_unapproved",
        "门诊资料尚未审核通过",
    )
    require(
        clinic.profile.get("business_contact") and clinic.profile.get("business_phone"),
        "contact_required",
        "门诊业务联系人信息待补充",
    )
    current_contract(clinic.organization_id, channel_id=clinic.channel_id)
    current_contract(clinic.channel_id, product_id=product_id)
    if product_id:
        require(
            Product.objects.filter(pk=product_id, status="active").exists(),
            "product_disabled",
            "产品已停用",
        )


@transaction.atomic
def set_service_status(actor, clinic_id, *, status, version, reason):
    actor.require_platform()
    clinic = get_clinic(actor, clinic_id, lock=True)
    check_version(clinic, version)
    require(
        status in {"online", "offline", "paused", "exited"} and reason.strip(),
        "invalid_status",
        "请选择上下线状态并填写原因",
        400,
    )
    if status == "online":
        require(
            clinic.service_status != "exited", "clinic_exited", "已退出门诊需重新建立合作后处理"
        )
        assert_new_business(clinic)
    clinic.service_status = status
    advance(clinic, "service_status")
    audit(actor, clinic, "clinic.service_status", reason=reason, status=status)
    return clinic


@transaction.atomic
def set_confirmation_hours(actor, clinic_id, *, hours, version, reason):
    actor.require_platform()
    clinic = get_clinic(actor, clinic_id, lock=True)
    check_version(clinic, version)
    require(
        type(hours) is int and 1 <= hours <= 168 and reason.strip(),
        "invalid_hours",
        "时限必须为1～168小时并填写原因",
        400,
    )
    clinic.confirmation_hours = hours
    advance(clinic, "confirmation_hours")
    audit(actor, clinic, "clinic.confirmation_hours", reason=reason, hours=hours)
    return clinic


@transaction.atomic
def set_clinic_product(actor, clinic_id, *, product_id, online, reason):
    clinic = get_clinic(actor, clinic_id, lock=True, edit=True)
    require(
        isinstance(online, bool) and reason.strip(),
        "invalid_product",
        "请确认产品上下线及原因",
        400,
    )
    product = Product.objects.filter(pk=product_id).first()
    require(product, "not_found", "推广产品不存在", 404)
    if online:
        assert_new_business(clinic, product.id)
    link, _ = ClinicProduct.objects.get_or_create(clinic=clinic, product=product)
    link.status = "online" if online else "offline"
    advance(link, "status")
    audit(
        actor,
        clinic,
        "clinic.product_status",
        reason=reason,
        product_id=str(product.id),
        status=link.status,
    )
    return link


@transaction.atomic
def change_channel(actor, clinic_id, *, channel_id, responsible_id, version, reason):
    actor.require_platform()
    clinic = get_clinic(actor, clinic_id, lock=True)
    check_version(clinic, version)
    require(clinic.service_status == "offline", "offline_required", "请先将门诊下线再变更渠道")
    require(
        not clinic.profile_changes.filter(status="pending").exists(),
        "pending_profile",
        "请先处理待审门诊资料",
    )
    channel = Organization.objects.filter(pk=channel_id, kind="channel", status="active").first()
    require(channel and reason.strip(), "invalid_channel", "请选择有效渠道并填写原因", 400)
    current_contract(channel.id)
    responsible = Membership.objects.filter(
        pk=responsible_id, organization=channel, active=True, account__active=True
    ).first()
    require(responsible, "invalid_responsible", "请选择新渠道有效业务员", 400)
    old = clinic.channel_id
    clinic.channel, clinic.responsible = channel, responsible
    clinic.profile = {**clinic.profile, "responsible_id": str(responsible.id)}
    advance(clinic, "channel", "responsible", "profile")
    ClinicProduct.objects.filter(clinic=clinic).update(status="offline")
    audit(
        actor,
        clinic,
        "clinic.channel_changed",
        reason=reason,
        previous_channel=str(old),
        channel_id=str(channel.id),
    )
    return clinic


def distance_km(lng1, lat1, lng2, lat2):
    values = [float(value) for value in (lng1, lat1, lng2, lat2)]
    require(all(math.isfinite(v) for v in values), "invalid_location", "坐标不合法", 400)
    a, b, c, d = map(math.radians, values)
    h = math.sin((d - b) / 2) ** 2 + math.cos(b) * math.cos(d) * math.sin((c - a) / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1, math.sqrt(h)))
