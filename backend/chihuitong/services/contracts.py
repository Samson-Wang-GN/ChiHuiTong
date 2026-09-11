from datetime import datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from chihuitong.errors import BusinessError, require
from chihuitong.models import (
    BusinessCalendar,
    Clinic,
    Contract,
    ContractProduct,
    ContractProductRevision,
    ContractVersion,
    Organization,
    Product,
)

from .common import RESOURCE_KINDS, advance, audit, check_version


def workday_due(start, days=2):
    date = timezone.localtime(start).date()
    count = 0
    while count < days:
        date += timedelta(days=1)
        override = BusinessCalendar.objects.filter(date=date).first()
        working = override.working if override else date.weekday() < 5
        count += int(working)
    return timezone.make_aware(datetime.combine(date, time(23, 59, 59)))


def accessible_contracts(actor):
    qs = Contract.objects.select_related("organization")
    if actor.platform:
        return qs
    if actor.organization.kind == "channel":
        clinic_qs = Clinic.objects.filter(channel=actor.organization)
        if actor.membership.role != "admin":
            clinic_qs = clinic_qs.filter(responsible=actor.membership)
        from django.db.models import Q

        return qs.filter(
            Q(organization=actor.organization)
            | Q(organization_id__in=clinic_qs.values("organization_id"))
        )
    if actor.organization.kind == "clinic":
        actor.require_admin()
    return qs.filter(organization=actor.organization)


def current_contract(org_id, *, at=None, product_id=None, stock=False, channel_id=None):
    at = at or timezone.now()
    qs = ContractVersion.objects.select_related("contract", "contract__organization").filter(
        contract__organization_id=org_id,
        status__in=["approved", "terminated"],
        starts_at__lte=at,
        reviewed_at__lte=at,
    )
    if channel_id:
        qs = qs.filter(channel_id=channel_id)
    if not stock:
        qs = qs.filter(contract__organization__status="active")
    if product_id and stock:
        # Disabling a product stops new business, never removes existing service terms.
        qs = qs.filter(products__product_id=product_id)
    chosen = qs.order_by("-starts_at", "-revision").first()
    require(chosen, "contract_unavailable", "缺少适用的已审核合同或推广产品条款，请联系平台核对")
    if not stock:
        require(
            chosen.status == "approved", "contract_terminated", "当前合同已终止，暂不能开展新业务"
        )
        require(chosen.ends_at >= at, "contract_expired", "当前合同已到期，暂不能开展新业务")
        if product_id:
            require(
                chosen.products.filter(product_id=product_id, status="active").exists(),
                "product_unauthorized",
                "当前合同未授权此推广产品",
            )
    return chosen


def validate_contract_data(data):
    require(
        set(data) == {"starts_at", "ends_at", "settlement_cycle", "contact", "attachment_ids"},
        "invalid_fields",
        "合同字段不完整或包含不允许字段",
        400,
    )
    start, end = data["starts_at"], data["ends_at"]
    require(
        isinstance(start, datetime)
        and isinstance(end, datetime)
        and timezone.is_aware(start)
        and timezone.is_aware(end)
        and end > start,
        "invalid_dates",
        "合同起止日期不合法",
        400,
    )
    require(
        data["settlement_cycle"] in {"weekly", "monthly"}, "invalid_cycle", "请选择周结或月结", 400
    )
    contact = data["contact"]
    require(
        isinstance(contact, dict)
        and set(contact) == {"name", "phone"}
        and str(contact["name"]).strip()
        and str(contact["phone"]).strip(),
        "contact_required",
        "请填写合同联系人及电话",
        400,
    )
    from .clinics import normalize_business_phone

    normalize_business_phone(contact["phone"])
    require(
        isinstance(data["attachment_ids"], list) and data["attachment_ids"],
        "attachments_required",
        "请上传全部签署附件",
        400,
    )


@transaction.atomic
def create_version(actor, org_id, *, number, data):
    org = Organization.objects.select_for_update().filter(pk=org_id).first()
    require(org, "not_found", "机构不存在", 404)
    clinic = None
    if org.kind == "clinic":
        from .clinics import get_clinic

        clinic = get_clinic(actor, org.clinic.id)
        require(
            actor.platform or actor.organization.kind == "channel",
            "forbidden",
            "门诊合同由渠道提交、平台审核",
            403,
        )
    else:
        actor.require_platform()
    require(
        org.kind in RESOURCE_KINDS | {"channel", "clinic"},
        "invalid_kind",
        "此机构不支持合作合同",
        400,
    )
    validate_contract_data(data)
    from .files import validate_attachment_ids

    validate_attachment_ids(actor, data["attachment_ids"], purposes={"contract"})
    kind = "resource" if org.kind in RESOURCE_KINDS else org.kind
    require(
        isinstance(number, str) and 0 < len(number.strip()) <= 80,
        "number_required",
        "请填写合同编号",
        400,
    )
    contract, created = Contract.objects.get_or_create(
        organization=org, defaults={"kind": kind, "number": number.strip()}
    )
    require(
        created or contract.number == number.strip(),
        "master_contract_exists",
        "本机构已有唯一主合同，请沿用原合同编号",
    )
    require(
        not contract.versions.filter(status="pending").exists(),
        "pending_contract",
        "已有待审版本，请先处理",
    )
    if kind != "clinic":
        require(data["settlement_cycle"] == "monthly", "partner_monthly", "合作方统一月结", 400)
    revision = (
        contract.versions.order_by("-revision").values_list("revision", flat=True).first() or 0
    ) + 1
    version = ContractVersion.objects.create(
        contract=contract,
        revision=revision,
        channel=clinic.channel if clinic else None,
        submitted_by=actor.membership,
        **data,
    )
    from .files import link_files

    link_files(data["attachment_ids"], contract)
    audit(
        actor, contract, "contract.version_created", version_id=str(version.id), revision=revision
    )
    if clinic:
        audit(actor, clinic, "clinic.contract_created", contract_version=str(version.id))
    return version


@transaction.atomic
def submit_version(actor, version_id, *, version):
    allowed = accessible_contracts(actor)
    item = (
        ContractVersion.objects.select_for_update()
        .filter(pk=version_id, contract__in=allowed)
        .first()
    )
    require(item, "not_found", "合同版本不存在", 404)
    check_version(item, version)
    require(
        actor.platform or (actor.organization.kind == "channel" and item.contract.kind == "clinic"),
        "forbidden",
        "无权提交此合同",
        403,
    )
    require(item.status == "draft", "invalid_state", "仅草稿合同可提交")
    Contract.objects.select_for_update().get(pk=item.contract_id)
    require(
        not item.contract.versions.filter(status="pending").exists(),
        "pending_contract",
        "已有待审版本",
    )
    item.status, item.submitted_at = "pending", timezone.now()
    item.due_at = workday_due(item.submitted_at)
    advance(item, "status", "submitted_at", "due_at")
    audit(actor, item.contract, "contract.submitted", version_id=str(item.id))
    return item


@transaction.atomic
def review_version(actor, version_id, *, approved, version, reason):
    actor.require_platform()
    item = (
        ContractVersion.objects.select_for_update()
        .select_related("contract")
        .filter(pk=version_id)
        .first()
    )
    require(item, "not_found", "合同版本不存在", 404)
    check_version(item, version)
    require(item.status == "pending", "invalid_state", "仅待审合同可审核")
    require(
        isinstance(approved, bool) and reason.strip(),
        "reason_required",
        "请填写审核结论及意见",
        400,
    )
    Contract.objects.select_for_update().get(pk=item.contract_id)
    if approved:
        from .files import validate_attachment_ids

        validate_attachment_ids(actor, item.attachment_ids, purposes={"contract"})
        if item.contract.kind == "clinic":
            clinic = Clinic.objects.get(organization=item.contract.organization)
            require(
                item.channel_id == clinic.channel_id,
                "channel_changed",
                "门诊渠道已变更，请重新签订当前三方合同",
            )
        latest = (
            item.contract.versions.filter(status="approved")
            .order_by("-starts_at", "-revision")
            .first()
        )
        require(
            not latest or item.starts_at >= latest.starts_at,
            "backdated_contract",
            "不能用较早生效时间覆盖已审核的新合同",
        )
        # Earlier approved revisions remain immutable history. Selection picks the latest effective revision.
    item.status = "approved" if approved else "rejected"
    item.reviewed_by, item.reviewed_at, item.reason = actor.membership, timezone.now(), reason
    advance(item, "status", "reviewed_by", "reviewed_at", "reason")
    audit(
        actor,
        item.contract,
        "contract.reviewed",
        reason=reason,
        version_id=str(item.id),
        status=item.status,
    )
    if item.contract.kind == "clinic":
        audit(
            actor,
            Clinic.objects.get(organization=item.contract.organization),
            "clinic.contract_reviewed",
            reason=reason,
            version_id=str(item.id),
            status=item.status,
        )
    return item


def split_cents(fee_cents, mode, value):
    value = Decimal(str(value))
    require(
        value.is_finite() and value >= 0 and mode in {"percent", "amount"},
        "invalid_split",
        "分配设置不合法",
        400,
    )
    require(mode != "percent" or value <= 100, "invalid_split", "比例不能超过100%", 400)
    result = Decimal(fee_cents) * value / 100 if mode == "percent" else value * 100
    return int(result.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def term_snapshot(term):
    return {
        "id": str(term.id),
        "version": term.version,
        "contract_version_id": str(term.contract_version_id),
        "product_id": str(term.product_id),
        "mode": term.mode,
        "value": str(term.value),
        "status": term.status,
    }


@transaction.atomic
def save_term(
    actor, contract_version_id, *, product_id, mode, value, status="active", version=None, reason
):
    actor.require_platform()
    item = (
        ContractVersion.objects.select_for_update()
        .select_related("contract")
        .filter(pk=contract_version_id)
        .first()
    )
    require(item, "not_found", "合同版本不存在", 404)
    require(
        item.status in {"draft", "approved"}, "invalid_state", "待审、退回或终止合同不可配置产品"
    )
    require(
        item.contract.kind != "clinic",
        "clinic_terms",
        "门诊通过渠道授权管理产品，不配置合作方分配",
        400,
    )
    product = Product.objects.select_for_update().filter(pk=product_id).first()
    require(product, "not_found", "推广产品不存在", 404)
    require(
        status in {"active", "disabled"} and reason.strip(),
        "invalid_term",
        "请填写状态和配置原因",
        400,
    )
    try:
        require(
            not isinstance(value, (float, bool)), "invalid_split", "分配值使用十进制字符串", 400
        )
        amount = Decimal(str(value))
        require(
            amount.is_finite() and amount.as_tuple().exponent >= -4,
            "invalid_split",
            "分配值最多四位小数",
            400,
        )
        assigned = split_cents(product.fee_cents, mode, amount)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise BusinessError("invalid_split", "分配值不合法", 400) from exc
    require(assigned <= product.fee_cents, "overallocated", "本方分配不能超过获客费")
    # Check every active opposite-side rule; redemption repeats the actual combination check.
    opposite_kind = "channel" if item.contract.kind == "resource" else "resource"
    others = ContractProduct.objects.filter(
        product=product,
        status="active",
        contract_version__status="approved",
        contract_version__contract__kind=opposite_kind,
    )
    if status == "active":
        for other in others:
            require(
                assigned + split_cents(product.fee_cents, other.mode, other.value)
                <= product.fee_cents,
                "overallocated",
                "与已配置合作方组合后分配超过获客费",
            )
    term = ContractProduct.objects.filter(contract_version=item, product=product).first()
    if term:
        check_version(term, version)
        term.mode, term.value, term.status = mode, amount, status
        advance(term, "mode", "value", "status")
    else:
        require(version is None, "stale_version", "条款不存在，请重新添加")
        term = ContractProduct.objects.create(
            contract_version=item, product=product, mode=mode, value=amount, status=status
        )
    ContractProductRevision.objects.create(
        term=term, revision=term.version, snapshot=term_snapshot(term)
    )
    audit(
        actor,
        item.contract,
        "contract.product_configured",
        reason=reason,
        term_id=str(term.id),
        term_version=term.version,
    )
    return term


def resolve_fees(resource_id, clinic, product, *, at=None):
    """Called inside redemption transaction after relevant rows are locked."""
    at = at or timezone.now()
    resource_contract = current_contract(resource_id, at=at, product_id=product.id, stock=True)
    channel_contract = current_contract(clinic.channel_id, at=at, product_id=product.id, stock=True)
    clinic_contract = current_contract(
        clinic.organization_id, at=at, stock=True, channel_id=clinic.channel_id
    )
    resource_term = resource_contract.products.get(product=product)
    channel_term = channel_contract.products.get(product=product)
    resource_amount = split_cents(product.fee_cents, resource_term.mode, resource_term.value)
    channel_amount = split_cents(product.fee_cents, channel_term.mode, channel_term.value)
    require(
        resource_amount + channel_amount <= product.fee_cents,
        "overallocated",
        "实际分配超过获客费，请平台核对",
    )
    return {
        "fee_cents": product.fee_cents,
        "resource_cents": resource_amount,
        "channel_cents": channel_amount,
        "platform_cents": product.fee_cents - resource_amount - channel_amount,
        "resource_id": str(resource_id),
        "channel_id": str(clinic.channel_id),
        "resource_term": term_snapshot(resource_term),
        "channel_term": term_snapshot(channel_term),
        "clinic_contract_id": str(clinic_contract.id),
        "product_version": product.version,
        "historical_fallback": {
            "resource": resource_contract.ends_at < at,
            "channel": channel_contract.ends_at < at,
            "clinic": clinic_contract.ends_at < at,
        },
    }
