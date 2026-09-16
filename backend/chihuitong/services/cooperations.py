"""Signatory and versioned store coverage; legacy clinic contracts remain immutable."""

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from chihuitong.errors import require
from chihuitong.models import (
    AgreementClinic,
    Clinic,
    ClinicAgreement,
    ClinicCooperation,
    InstantRedemptionOrder,
    Membership,
    Organization,
    Product,
)

from .common import advance, advisory_lock, audit, check_version
from .contracts import current_contract, workday_due


def visible_cooperations(actor):
    from .clinics import visible_clinics

    qs = ClinicCooperation.objects.select_related("organization", "created_by")
    if actor.platform:
        return qs
    if actor.organization.kind == "clinic":
        actor.require_admin()
        return qs.filter(
            Q(organization=actor.organization) | Q(clinics__organization=actor.organization)
        ).distinct()
    if actor.organization.kind == "channel":
        return qs.filter(
            Q(clinics__in=visible_clinics(actor)) | Q(created_by=actor.membership)
        ).distinct()
    return qs.none()


def get_cooperation(actor, cooperation_id, *, lock=False):
    qs = visible_cooperations(actor)
    ids = qs.values("id")
    qs = ClinicCooperation.objects.select_related("organization").filter(pk__in=ids)
    if lock:
        qs = qs.select_for_update(of=("self",))
    item = qs.filter(pk=cooperation_id).first()
    require(item, "not_found", "合作主体不存在或无权访问", 404)
    return item


def full_access(actor, item, agreement=None):
    if actor.platform or actor.organization.id == item.organization_id:
        return actor.platform or actor.membership.role == "admin"
    if (
        item.kind == "single"
        and actor.organization.kind == "clinic"
        and actor.membership.role == "admin"
    ):
        return item.clinics.filter(organization=actor.organization).exists()
    if actor.organization.kind != "channel":
        return False
    from .clinics import visible_clinics

    ids = agreement.coverage.values("clinic_id") if agreement else item.clinics.values("id")
    stores = Clinic.objects.filter(pk__in=ids)
    return not stores.exclude(pk__in=visible_clinics(actor).values("id")).exists() and (
        stores.exists() or item.created_by_id == actor.membership.id
    )


def assert_edit(actor, item):
    require(
        full_access(actor, item), "forbidden", "此操作需要签约主体完整管理范围，请联系平台", 403
    )


def assert_no_payment(clinic_ids):
    require(
        not InstantRedemptionOrder.objects.filter(
            appointment__clinic_id__in=clinic_ids, status__in=["pending", "paid"]
        ).exists(),
        "unresolved_payment",
        "门店仍有未决现付，请先核实支付及核销结果",
    )


@transaction.atomic
def create_cooperation(actor, *, name, kind, admin_name, admin_phone, credit_code):
    require(
        actor.platform or actor.organization.kind == "channel",
        "forbidden",
        "仅平台或渠道可登记合作主体",
        403,
    )
    require(
        kind in {"single", "chain"} and isinstance(name, str) and 0 < len(name.strip()) <= 160,
        "invalid_subject",
        "请填写签约主体全称并选择单店或连锁",
        400,
    )
    if not actor.platform:
        current_contract(actor.organization.id)
    import re

    from .organizations import account_for

    credit_code = credit_code.strip().upper()
    require(
        re.fullmatch(r"[0-9A-HJ-NPQRTUWXY]{18}", credit_code),
        "invalid_credit_code",
        "请填写18位统一社会信用代码",
        400,
    )
    advisory_lock("clinic_signatory", credit_code)
    require(
        not ClinicCooperation.objects.filter(credit_code=credit_code).exists(),
        "subject_exists",
        "此签约主体已登记，请选择已有主体；无权限时请联系平台",
        409,
    )
    org = Organization.objects.create(name=name.strip(), kind="clinic")
    item = ClinicCooperation.objects.create(
        organization=org, kind=kind, created_by=actor.membership, credit_code=credit_code
    )
    Membership.objects.create(
        organization=org,
        account=account_for(admin_phone, admin_name),
        role="admin",
        platform_created=True,
    )
    audit(actor, item, "cooperation.created", kind=kind)
    return item


@transaction.atomic
def attach_clinic(actor, cooperation_id, clinic_id, *, version, reason):
    from .clinics import get_clinic

    actor.require_platform()
    item = get_cooperation(actor, cooperation_id, lock=True)
    clinic = get_clinic(actor, clinic_id, lock=True)
    check_version(clinic, version)
    require(
        clinic.service_status == "offline" and reason.strip(),
        "offline_required",
        "请先下线并填写门店关联原因",
    )
    assert_no_payment([clinic.id])
    require(
        item.kind == "chain" or not item.clinics.exclude(pk=clinic.id).exists(),
        "single_store_only",
        "单店主体只能关联一家门店",
    )
    require(
        not clinic.cooperation_id or clinic.cooperation_id == item.id,
        "subject_transfer_deferred",
        "已有签约主体的转移需另行核对存量承担，不允许直接改挂",
    )
    clinic.cooperation = item
    advance(clinic, "cooperation")
    audit(actor, clinic, "clinic.cooperation_attached", reason=reason, cooperation_id=str(item.id))
    return clinic


def current_agreement(item, *, at=None, stock=False):
    at = at or timezone.now()
    agreement = (
        item.agreements.filter(
            status__in=["approved", "terminated"], starts_at__lte=at, reviewed_at__lte=at
        )
        .order_by("-starts_at", "-revision")
        .first()
    )
    require(agreement, "contract_unavailable", "缺少已生效的双方合同，请完成签署及审核")
    if not stock:
        require(
            agreement.status == "approved"
            and agreement.ends_at >= at
            and item.status == "active"
            and item.organization.status == "active",
            "contract_inactive",
            "双方合同未生效、已到期或已终止",
        )
    return agreement


def clinic_agreement(clinic, *, stock=False, at=None, product_id=None):
    if not clinic.cooperation_id:
        require(
            clinic.contract_policy == "legacy",
            "contract_unavailable",
            "请先在合同管理关联门店并完成合同签署",
        )
        return current_contract(
            clinic.organization_id, at=at, stock=stock, channel_id=clinic.channel_id
        )
    if stock:
        at = at or timezone.now()
        qs = clinic.cooperation.agreements.filter(
            status__in=["approved", "terminated"],
            starts_at__lte=at,
            reviewed_at__lte=at,
            coverage__clinic=clinic,
        )
        if product_id:
            qs = qs.filter(product_ids__contains=[str(product_id)])
        agreement = qs.order_by("-starts_at", "-revision").first()
        require(agreement, "contract_unavailable", "没有覆盖此门店及产品的已签合同")
    else:
        agreement = current_agreement(clinic.cooperation, at=at, stock=False)
    require(
        agreement.coverage.filter(clinic=clinic).exists(),
        "clinic_not_covered",
        "当前双方合同未覆盖此门店，请联系平台核对",
    )
    if product_id:
        require(
            str(product_id) in agreement.product_ids,
            "product_not_covered",
            "双方合同未包含此推广产品",
        )
    return agreement


def assert_payment_ready():
    # The simulator is an explicit acceptance environment, never a production fallback.
    if settings.ACCEPTANCE_SIMULATED_EXTERNALS and settings.ENVIRONMENT != "production":
        return
    require(
        getattr(settings, "INSTANT_PAYMENT_ACCEPTED", False),
        "instant_not_ready",
        "现付收款尚未完成真实验收，暂不能上线",
    )
    from .payments import payment_gateway

    payment_gateway()


def validate_data(actor, item, data):
    from .clinics import normalize_business_phone, visible_clinics
    from .files import validate_attachment_ids

    require(data["ends_at"] > data["starts_at"], "invalid_dates", "合同结束日期须晚于生效日期", 400)
    mode = "instant" if item.kind == "single" else "postpaid"
    require(
        data["payment_mode"] == mode
        and (
            data["settlement_cycle"] == ""
            if mode == "instant"
            else data["settlement_cycle"] in {"weekly", "monthly"}
        ),
        "invalid_payment_mode",
        "单店固定核销现付；连锁请选择周结或月结",
        400,
    )
    normalize_business_phone(data["contact"]["phone"])
    ids = {str(value) for value in data["clinic_ids"]}
    require(
        len(ids) == len(data["clinic_ids"]),
        "coverage_required",
        "请选择不重复的覆盖门店",
        400,
    )
    stores = Clinic.objects.select_for_update().filter(pk__in=ids).order_by("id")
    require(stores.count() == len(ids), "coverage_invalid", "覆盖门店不存在", 400)
    require(
        not stores.exclude(
            Q(cooperation=item) | Q(cooperation__isnull=True, contract_policy="bilateral")
        ).exists(),
        "coverage_invalid",
        "不能在草稿中转移其他主体或历史门店，请联系平台",
        400,
    )
    require(
        not stores.exclude(pk__in=visible_clinics(actor).values("id")).exists(),
        "forbidden",
        "不能提交超出本人范围的合同覆盖，请平台处理",
        403,
    )
    require(
        item.kind == "chain" or len(ids) <= 1, "single_store_only", "单店合同只覆盖一家门店", 400
    )
    products = {str(value) for value in data["product_ids"]}
    require(
        products
        and Product.objects.filter(pk__in=products, status="active").count() == len(products),
        "invalid_products",
        "请选择有效推广产品",
        400,
    )
    for store in stores:
        for product_id in products:
            current_contract(store.channel_id, product_id=product_id)
    if data["attachment_ids"]:
        validate_attachment_ids(actor, data["attachment_ids"], purposes={"contract"})
    assert_no_payment(ids)
    require(
        item.kind == "chain" or not item.clinics.exclude(pk__in=ids).exists(),
        "single_store_only",
        "单店主体已关联其他门店",
    )
    for store in stores:
        if not store.cooperation_id:
            require(store.service_status != "online", "clinic_online", "关联签约主体前须下线")
            store.cooperation = item
            advance(store, "cooperation")
            audit(
                actor,
                store,
                "clinic.cooperation_attached",
                cooperation_id=str(item.id),
                reason="合同关联门店",
            )
    return sorted(ids), sorted(products)


@transaction.atomic
def start_agreement(actor, *, data, cooperation_id=None, subject=None):
    require(
        bool(cooperation_id) != bool(subject), "subject_required", "请选择已有主体或填写新主体", 400
    )
    if subject:
        cooperation_id = create_cooperation(actor, **subject).id
    return save_agreement(actor, cooperation_id, data=data)


@transaction.atomic
def save_agreement(actor, cooperation_id, *, data, agreement_id=None, version=None):
    item = get_cooperation(actor, cooperation_id, lock=True)
    assert_edit(actor, item)
    ids, products = validate_data(actor, item, data)
    if agreement_id:
        agreement = item.agreements.select_for_update().filter(pk=agreement_id).first()
        require(agreement, "not_found", "合同不存在", 404)
        check_version(agreement, version)
        require(agreement.status == "draft", "invalid_state", "只可编辑草稿，退回后请新建修订版本")
    else:
        require(
            not item.agreements.filter(status__in=["draft", "pending"]).exists(),
            "pending_agreement",
            "请先处理现有草稿或待审合同",
        )
        revision = (
            item.agreements.order_by("-revision").values_list("revision", flat=True).first() or 0
        ) + 1
        agreement = ClinicAgreement(
            cooperation=item, revision=revision, submitted_by=actor.membership
        )
    for key in [
        "number",
        "starts_at",
        "ends_at",
        "payment_mode",
        "settlement_cycle",
        "contact",
        "attachment_ids",
    ]:
        setattr(agreement, key, data[key])
    agreement.product_ids = products
    if agreement_id:
        advance(
            agreement,
            "number",
            "starts_at",
            "ends_at",
            "payment_mode",
            "settlement_cycle",
            "contact",
            "attachment_ids",
            "product_ids",
        )
        agreement.coverage.all().delete()
    else:
        agreement.save()
    AgreementClinic.objects.bulk_create(
        [AgreementClinic(agreement=agreement, clinic_id=pk) for pk in ids]
    )
    from .files import link_files

    link_files(agreement.attachment_ids, agreement)
    audit(actor, agreement, "agreement.saved", revision=agreement.revision, clinic_ids=ids)
    return agreement


def get_agreement(actor, agreement_id, *, lock=False):
    qs = ClinicAgreement.objects.select_related("cooperation__organization").filter(
        cooperation__in=visible_cooperations(actor)
    )
    if lock:
        qs = qs.select_for_update(of=("self",))
    value = qs.filter(pk=agreement_id).first()
    require(value, "not_found", "合同不存在或无权访问", 404)
    return value


@transaction.atomic
def submit_agreement(actor, agreement_id, *, version):
    ref = get_agreement(actor, agreement_id)
    ClinicCooperation.objects.select_for_update().get(pk=ref.cooperation_id)
    item = get_agreement(actor, agreement_id, lock=True)
    assert_edit(actor, item.cooperation)
    check_version(item, version)
    require(item.status == "draft", "invalid_state", "仅草稿可提交审核")
    require(item.attachment_ids, "signature_required", "请上传完整门诊签署件后再提交审核", 409)
    require(
        not item.cooperation.agreements.filter(status="pending").exists(),
        "pending_agreement",
        "已有待审核合同",
    )
    item.status, item.submitted_at = "pending", timezone.now()
    item.due_at = workday_due(item.submitted_at)
    advance(item, "status", "submitted_at", "due_at")
    audit(actor, item, "agreement.submitted")
    return item


@transaction.atomic
def record_paper(actor, agreement_id, *, version, data):
    item = get_agreement(actor, agreement_id, lock=True)
    check_version(item, version)
    assert_edit(actor, item.cooperation)
    require(item.status in {"draft", "pending", "approved"}, "invalid_state", "此合同不可办理原件")
    allowed = {
        "outbound_carrier",
        "outbound_tracking",
        "recipient",
        "recipient_phone",
        "return_address",
    }
    if actor.platform:
        allowed |= {
            "received_at",
            "platform_signed_at",
            "return_carrier",
            "return_tracking",
            "returned_at",
        }
    require(
        not (set(data) - allowed - ({"signed_attachment_ids"} if actor.platform else set())),
        "forbidden",
        "无权修改平台收签或寄回记录",
        403,
    )
    require(
        item.status != "approved"
        or set(data) <= {"return_carrier", "return_tracking", "returned_at"},
        "signed_immutable",
        "生效签署记录不可覆盖，只能补充寄回物流",
    )
    if "signed_attachment_ids" in data:
        from .files import link_files, validate_attachment_ids

        validate_attachment_ids(actor, data["signed_attachment_ids"], purposes={"contract"})
        item.signed_attachment_ids = data["signed_attachment_ids"]
        link_files(item.signed_attachment_ids, item)
    item.paper = {**item.paper, **{k: v for k, v in data.items() if k != "signed_attachment_ids"}}
    from datetime import datetime

    dates = [
        datetime.fromisoformat(item.paper[k])
        for k in ["received_at", "platform_signed_at", "returned_at"]
        if item.paper.get(k)
    ]
    require(
        all(d <= timezone.now() for d in dates) and dates == sorted(dates),
        "invalid_paper_dates",
        "收件、签署、寄回时间须按顺序且不能是未来时间",
        400,
    )
    advance(item, "paper", "signed_attachment_ids")
    audit(actor, item, "agreement.paper_updated", fields=sorted(data))
    return item


@transaction.atomic
def review_agreement(actor, agreement_id, *, version, approved, reason, final=False, joint=False):
    actor.require_platform()
    ref = get_agreement(actor, agreement_id)
    ClinicCooperation.objects.select_for_update().get(pk=ref.cooperation_id)
    list(
        Clinic.objects.select_for_update().filter(cooperation_id=ref.cooperation_id).order_by("id")
    )
    item = get_agreement(actor, agreement_id, lock=True)
    check_version(item, version)
    require(
        not item.onboarding_change_id or joint,
        "joint_review_required",
        "此合同属于单店入驻申请，请统一审核",
    )
    require(
        item.status == "pending" and reason.strip(),
        "invalid_state",
        "仅待审核合同可处理，请填写审核意见",
    )
    if approved:
        from .files import validate_attachment_ids

        validate_attachment_ids(actor, item.attachment_ids, purposes={"contract"})
        item.content_status = "approved"
        if final:
            require(
                item.paper.get("received_at") and item.paper.get("platform_signed_at"),
                "signature_required",
                "请先登记原件收件及平台签署时间",
            )
            validate_attachment_ids(actor, item.signed_attachment_ids, purposes={"contract"})
            require(
                item.cooperation.kind == "chain" or item.coverage.exists(),
                "coverage_required",
                "单店合同缺少覆盖门店",
            )
            # Lock the covered clinics before checking any in-flight payment.
            clinic_ids = list(item.coverage.values_list("clinic_id", flat=True))
            stores = list(
                Clinic.objects.select_for_update().filter(pk__in=clinic_ids).order_by("id")
            )
            assert_no_payment(clinic_ids)
            require(
                all(store.cooperation_id == item.cooperation_id for store in stores),
                "coverage_changed",
                "覆盖门店主体已变化，请重新提交",
            )
            for store in stores:
                for product_id in item.product_ids:
                    current_contract(store.channel_id, product_id=product_id)
            previous = (
                item.cooperation.agreements.filter(status__in=["approved", "terminated"])
                .order_by("-starts_at", "-revision")
                .first()
            )
            require(
                not previous or item.starts_at >= previous.starts_at,
                "backdated_contract",
                "不能回溯覆盖较新生效版本",
            )
            item.status, item.reviewed_at, item.reviewed_by = (
                "approved",
                timezone.now(),
                actor.membership,
            )
    else:
        item.status, item.content_status = "rejected", "rejected"
        item.reviewed_at, item.reviewed_by = timezone.now(), actor.membership
    item.reason = reason
    advance(item, "status", "content_status", "reviewed_at", "reviewed_by", "reason")
    audit(actor, item, "agreement.reviewed", reason=reason, final=final, status=item.status)
    return item


@transaction.atomic
def terminate_agreement(actor, agreement_id, *, version, reason):
    actor.require_platform()
    ref = get_agreement(actor, agreement_id)
    ClinicCooperation.objects.select_for_update().get(pk=ref.cooperation_id)
    list(
        Clinic.objects.select_for_update().filter(cooperation_id=ref.cooperation_id).order_by("id")
    )
    item = get_agreement(actor, agreement_id, lock=True)
    check_version(item, version)
    require(
        item.status == "approved" and reason.strip(),
        "invalid_state",
        "仅生效合同可终止，请填写原因",
    )
    stores = list(item.coverage.values_list("clinic_id", flat=True))
    list(Clinic.objects.select_for_update().filter(pk__in=stores).order_by("id"))
    assert_no_payment(stores)
    item.status, item.reason = "terminated", reason
    advance(item, "status", "reason")
    audit(actor, item, "agreement.terminated", reason=reason)
    return item


def batch_online(actor, clinic_ids, *, reason):
    from chihuitong.errors import BusinessError

    from .clinics import get_clinic, set_service_status

    actor.require_platform()
    require(
        reason.strip() and 0 < len(clinic_ids) <= 100,
        "invalid_batch",
        "请选择1～100家门店并填写原因",
        400,
    )
    results = []
    for clinic_id in dict.fromkeys(clinic_ids):
        try:
            with transaction.atomic():
                clinic = get_clinic(actor, clinic_id, lock=True)
                set_service_status(
                    actor, clinic.id, status="online", version=clinic.version, reason=reason
                )
            results.append({"id": str(clinic_id), "status": "online"})
        except BusinessError as exc:
            results.append({"id": str(clinic_id), "status": "blocked", "message": exc.message})
    return results
