from django.db import transaction

from chihuitong.crypto import digest, masked_phone, normalize_phone
from chihuitong.errors import require
from chihuitong.models import Account, Membership, Organization

from .common import RESOURCE_KINDS, advance, advisory_lock, audit, check_version


def account_for(phone, name):
    phone = normalize_phone(phone)
    require(
        isinstance(name, str) and 0 < len(name.strip()) <= 100,
        "invalid_name",
        "请输入账号姓名",
        400,
    )
    index = digest(phone, purpose="phone")
    advisory_lock("account", index)
    account, _ = Account.objects.get_or_create(
        phone_index=index, defaults={"phone": phone, "name": name.strip()}
    )
    require(account.active, "account_disabled", "此账号已停用，请联系平台")
    return account


@transaction.atomic
def create_organization(
    actor, *, name, kind, admin_name, admin_phone, contact_name=None, contact_phone=None
):
    actor.require_platform()
    require(
        kind in RESOURCE_KINDS | {"channel"}, "invalid_kind", "请选择客户资源方或渠道机构类型", 400
    )
    require(
        isinstance(name, str) and 0 < len(name.strip()) <= 200,
        "invalid_name",
        "请输入机构名称",
        400,
    )
    contact = contact_name if contact_name is not None else admin_name
    require(
        isinstance(contact, str) and 1 <= len(contact.strip()) <= 100,
        "invalid_contact",
        "请填写机构联系人",
        400,
    )
    phone = normalize_phone(contact_phone if contact_phone is not None else admin_phone)
    org = Organization.objects.create(
        name=name.strip(),
        kind=kind,
        status="pending",
        details={"contact_name": contact.strip(), "contact_phone": phone},
    )
    account = account_for(admin_phone, admin_name)
    member = Membership.objects.create(
        organization=org, account=account, role="admin", platform_created=True
    )
    audit(actor, org, "organization.created", initial_admin=str(member.id))
    audit(actor, member, "membership.created", role="admin", platform_created=True)
    return org


def managed_org(actor, org_id):
    actor.require_admin()
    qs = Organization.objects.all()
    if not actor.platform:
        qs = qs.filter(pk=actor.organization.pk)
    org = qs.filter(pk=org_id).first()
    require(org, "not_found", "机构不存在或无权访问", 404)
    return org


@transaction.atomic
def create_member(actor, org_id, *, name, phone, role):
    org = managed_org(actor, org_id)
    # Organization lock serializes member changes/last-admin checks.
    org = Organization.objects.select_for_update().get(pk=org.pk)
    require(org.status == "active", "organization_disabled", "机构已停用")
    require(role in {"admin", "staff"}, "invalid_role", "请选择管理员或员工/业务员", 400)
    if org.kind == "platform":
        actor.require_platform()
        require(role == "admin", "invalid_role", "本期平台仅支持管理员", 400)
    account = account_for(phone, name)
    require(
        not Membership.objects.filter(organization=org, account=account).exists(),
        "duplicate_member",
        "此机构已存在该手机号账号",
    )
    member = Membership.objects.create(organization=org, account=account, role=role)
    audit(actor, member, "membership.created", role=role)
    return member


@transaction.atomic
def update_member(actor, member_id, *, role, active, version, reason):
    actor.require_admin()
    member = Membership.objects.select_related("organization").filter(pk=member_id).first()
    require(member, "not_found", "账号不存在", 404)
    org = managed_org(actor, member.organization_id)
    Organization.objects.select_for_update().get(pk=org.pk)
    member = Membership.objects.select_for_update().get(pk=member.pk)
    check_version(member, version)
    require(
        role in {"admin", "staff"} and isinstance(active, bool),
        "invalid_role",
        "身份或状态不合法",
        400,
    )
    require(bool(reason.strip()), "reason_required", "请填写变更原因", 400)
    require(
        not (member.id == actor.membership.id and (not active or role != member.role)),
        "self_change",
        "不能修改自己的身份或停用自己",
    )
    require(
        not member.platform_created or role == "admin",
        "protected_admin",
        "平台开通的管理员身份不可修改",
    )
    if member.active and member.role == "admin" and (not active or role != "admin"):
        require(
            Membership.objects.filter(organization=org, active=True, role="admin")
            .exclude(pk=member.pk)
            .exists(),
            "last_admin",
            "不能停用或降级最后一个管理员",
        )
    require(org.kind != "platform" or role == "admin", "invalid_role", "平台账号必须为管理员")
    member.role, member.active = role, active
    advance(member, "role", "active")
    audit(actor, member, "membership.updated", reason=reason, role=role, active=active)
    return member


@transaction.atomic
def set_organization_status(actor, org_id, *, status, version, reason):
    actor.require_platform()
    org = Organization.objects.select_for_update().filter(pk=org_id).first()
    require(org, "not_found", "机构不存在", 404)
    check_version(org, version)
    require(org.kind != "platform", "protected_platform", "不能停用平台机构")
    require(org.kind != "clinic", "clinic_status_flow", "门诊服务状态请从门诊管理操作")
    require(
        org.status in {"active", "disabled"},
        "review_required",
        "机构必须先完成审核，不可通过启用绕过审核",
    )
    require(
        status in {"active", "disabled"} and reason.strip(),
        "invalid_status",
        "请选择状态并填写原因",
        400,
    )
    org.status = status
    advance(org, "status")
    audit(actor, org, "organization.status", reason=reason, status=status)
    return org


@transaction.atomic
def update_organization(actor, org_id, *, name, contact_name, contact_phone, version, reason):
    actor.require_platform()
    org = (
        Organization.objects.select_for_update()
        .filter(pk=org_id, kind__in=RESOURCE_KINDS | {"channel"})
        .first()
    )
    require(org, "not_found", "合作机构不存在", 404)
    check_version(org, version)
    require(
        isinstance(name, str)
        and 1 <= len(name.strip()) <= 200
        and isinstance(contact_name, str)
        and 1 <= len(contact_name.strip()) <= 100
        and isinstance(reason, str)
        and reason.strip(),
        "invalid_organization",
        "请补齐名称、联系人及修改原因",
        400,
    )
    org.name = name.strip()
    org.details = {
        **org.details,
        "contact_name": contact_name.strip(),
        "contact_phone": normalize_phone(contact_phone),
    }
    advance(org, "name", "details")
    audit(
        actor,
        org,
        "organization.updated",
        reason=reason,
        fields=["name", "contact_name", "contact_phone"],
    )
    return org


@transaction.atomic
def review_organization(actor, org_id, *, approved, version, reason):
    actor.require_platform()
    org = (
        Organization.objects.select_for_update()
        .filter(pk=org_id, kind__in=RESOURCE_KINDS | {"channel"})
        .first()
    )
    require(org, "not_found", "合作机构不存在", 404)
    check_version(org, version)
    require(
        org.status == "pending"
        and type(approved) is bool
        and isinstance(reason, str)
        and reason.strip(),
        "invalid_review",
        "请选择待审机构并填写审核意见",
        400,
    )
    org.status = "active" if approved else "rejected"
    advance(org, "status")
    audit(actor, org, "organization.reviewed", reason=reason, status=org.status)
    return org


@transaction.atomic
def resubmit_organization(actor, org_id, *, version, reason):
    actor.require_platform()
    org = (
        Organization.objects.select_for_update()
        .filter(pk=org_id, kind__in=RESOURCE_KINDS | {"channel"})
        .first()
    )
    require(org, "not_found", "合作机构不存在", 404)
    check_version(org, version)
    require(
        org.status == "rejected" and isinstance(reason, str) and reason.strip(),
        "invalid_state",
        "仅退回机构可以重新提交，请填写原因",
        400,
    )
    org.status = "pending"
    advance(org, "status")
    audit(actor, org, "organization.resubmitted", reason=reason)
    return org


def member_projection(member):
    return {
        "id": str(member.id),
        "organization_id": str(member.organization_id),
        "name": member.account.name,
        "phone": masked_phone(member.account.phone),
        "role": member.role,
        "active": member.active,
        "platform_created": member.platform_created,
        "version": member.version,
    }
