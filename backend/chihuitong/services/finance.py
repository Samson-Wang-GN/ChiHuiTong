from datetime import datetime, time, timedelta

from django.db import transaction
from django.utils import timezone

from chihuitong.crypto import digest
from chihuitong.errors import require
from chihuitong.models import (
    BillRevision,
    Clinic,
    ClinicBill,
    ClinicBillLine,
    ClinicReceipt,
    FinanceFeedback,
    PartnerBill,
    PartnerBillLine,
    PartnerPayment,
    ReceiptLedger,
    Redemption,
)

from .clinics import visible_clinics
from .common import advance, advisory_lock, audit, check_version
from .contracts import current_contract
from .files import link_files, validate_attachment_ids


def due_at(issued_on, cycle):
    date = issued_on + timedelta(days=3 if cycle == "weekly" else 5)
    return timezone.make_aware(datetime.combine(date, time(23, 59, 59)))


def visible_clinic_bills(actor):
    if actor.organization.kind == "clinic":
        actor.require_admin()
    return ClinicBill.objects.select_related("clinic__organization").filter(
        clinic__in=visible_clinics(actor)
    )


def get_bill(actor, bill_id, *, lock=False, pay=False):
    qs = visible_clinic_bills(actor)
    if lock:
        qs = qs.select_for_update(of=("self",))
    bill = qs.filter(pk=bill_id).first()
    require(bill, "not_found", "门诊账单不存在或无权访问", 404)
    if pay:
        actor.require_admin()
        require(
            actor.organization.kind == "clinic"
            and actor.organization.id == bill.clinic.organization_id,
            "forbidden",
            "仅本门诊管理员可提交付款",
            403,
        )
    return bill


def snapshot_bill(bill):
    BillRevision.objects.create(
        bill=bill,
        revision=bill.version,
        snapshot={
            "total_cents": bill.total_cents,
            "received_cents": bill.received_cents,
            "status": bill.status,
            "line_ids": [
                str(value) for value in bill.lines.filter(active=True).values_list("id", flat=True)
            ],
        },
    )


def effective_bill_status(bill, *, now=None):
    if bill.status in {"settled", "cancelled", "no_payment"}:
        return bill.status
    if (now or timezone.now()) > bill.due_at:
        return "overdue"
    if bill.dispute:
        return "disputed"
    if (
        bill.receipts.filter(status="pending").exists()
        or bill.payment_attempts.filter(status__in=["creating", "pending", "unknown"]).exists()
    ):
        return "payment_review"
    return "pending_payment"


@transaction.atomic
def generate_clinic_bill(clinic_id, *, issued_on):
    clinic = Clinic.objects.select_for_update().get(pk=clinic_id)
    contract = current_contract(clinic.organization_id, stock=True, channel_id=clinic.channel_id)
    cycle = contract.settlement_cycle
    require(
        (cycle == "weekly" and issued_on.weekday() == 0)
        or (cycle == "monthly" and issued_on.day == 1),
        "not_issue_day",
        "尚未到当前合同出账日",
    )
    existing = ClinicBill.objects.filter(clinic=clinic, issued_on=issued_on).first()
    if existing:
        return existing
    cutoff = timezone.make_aware(datetime.combine(issued_on, time.min))
    records = list(
        Redemption.objects.select_for_update()
        .filter(
            appointment__clinic=clinic,
            status="active",
            settled_at__isnull=True,
            created_at__lt=cutoff,
        )
        .exclude(bill_lines__active=True)
        .order_by("created_at", "id")
    )
    if not records:
        return None
    total = sum(record.fee_cents for record in records)
    bill = ClinicBill.objects.create(
        clinic=clinic,
        cycle=cycle,
        period_end=issued_on - timedelta(days=1),
        issued_on=issued_on,
        due_at=due_at(issued_on, cycle),
        total_cents=total,
        contract_version=contract.id,
        status="open" if total else "no_payment",
    )
    ClinicBillLine.objects.bulk_create(
        [
            ClinicBillLine(bill=bill, redemption=record, amount_cents=record.fee_cents)
            for record in records
        ]
    )
    snapshot_bill(bill)
    audit(None, bill, "bill.generated", total_cents=total, cycle=cycle, count=len(records))
    return bill


@transaction.atomic
def submit_receipt(
    actor, bill_id, *, amount_cents, paid_at, payer, reference, attachment_ids, version
):
    bill = get_bill(actor, bill_id, lock=True, pay=True)
    check_version(bill, version)
    require(bill.status == "open", "invalid_state", "账单已结清或停止收款")
    require(
        not bill.receipts.filter(status="pending").exists()
        and not bill.payment_attempts.filter(
            status__in=["creating", "pending", "unknown"]
        ).exists(),
        "unresolved_payment",
        "已有未决支付或待审凭证，请先核实",
    )
    require(
        type(amount_cents) is int and 0 < amount_cents <= bill.total_cents - bill.received_cents,
        "invalid_amount",
        "付款金额不能超过剩余应付",
        400,
    )
    require(
        isinstance(paid_at, datetime) and timezone.is_aware(paid_at) and paid_at <= timezone.now(),
        "invalid_paid_at",
        "请填写实际付款时间",
        400,
    )
    require(
        isinstance(reference, str)
        and reference.strip()
        and isinstance(payer, str)
        and payer.strip(),
        "receipt_required",
        "请填写付款方及流水号",
        400,
    )
    validate_attachment_ids(actor, attachment_ids, purposes={"payment"})
    receipt = ClinicReceipt.objects.create(
        bill=bill,
        bill_version=bill.version,
        amount_cents=amount_cents,
        paid_at=paid_at,
        payer=payer,
        reference=reference,
        reference_index=digest(reference.strip(), purpose="bank_reference"),
        attachment_ids=attachment_ids,
        submitted_by=actor.membership,
    )
    link_files(attachment_ids, bill)
    audit(
        actor, bill, "bill.receipt_submitted", receipt_id=str(receipt.id), amount_cents=amount_cents
    )
    return receipt


def settle_if_full(bill):
    if bill.status == "open" and bill.total_cents > 0 and bill.received_cents == bill.total_cents:
        bill.status, bill.settled_at = "settled", timezone.now()
        Redemption.objects.filter(
            bill_lines__bill=bill, bill_lines__active=True, status="active"
        ).update(settled_at=bill.settled_at)
        return True
    return False


def record_funds(bill, *, reference_index, amount_cents, received_at, kind, source_id, force_anomaly=""):
    """Caller holds bill lock. Real extra money is persisted as an anomaly, never discarded."""
    advisory_lock("receipt", reference_index)
    old = ReceiptLedger.objects.filter(reference_index=reference_index).first()
    if old:
        require(
            old.source_id == source_id and old.amount_cents == amount_cents,
            "duplicate_receipt",
            "该资金流水已用于其他收款记录",
        )
        return old
    anomaly = force_anomaly or (
        ""
        if bill.status == "open" and amount_cents <= bill.total_cents - bill.received_cents
        else "excess_or_closed"
    )
    ledger = ReceiptLedger.objects.create(
        reference_index=reference_index,
        kind=kind,
        source_id=source_id,
        bill=bill,
        amount_cents=amount_cents,
        received_at=received_at,
        anomaly=anomaly,
    )
    if not anomaly:
        bill.received_cents += amount_cents
        settled = settle_if_full(bill)
        advance(bill, "received_cents", "status", "settled_at")
        snapshot_bill(bill)
        if settled:
            audit(None, bill, "bill.settled", amount_cents=bill.total_cents)
    return ledger


@transaction.atomic
def review_receipt(actor, receipt_id, *, approved, version, reason):
    actor.require_platform()
    ref = ClinicReceipt.objects.filter(pk=receipt_id).first()
    require(ref, "not_found", "付款凭证不存在", 404)
    bill = ClinicBill.objects.select_for_update().get(pk=ref.bill_id)
    receipt = ClinicReceipt.objects.select_for_update().get(pk=receipt_id)
    check_version(receipt, version)
    require(
        receipt.status == "pending"
        and bill.status == "open"
        and bill.version == receipt.bill_version,
        "stale_bill",
        "凭证已处理或账单版本已变化，请重新核对",
    )
    require(
        type(approved) is bool and reason.strip(), "reason_required", "请填写实际到账核对意见", 400
    )
    if approved:
        validate_attachment_ids(actor, receipt.attachment_ids, purposes={"payment"})
        require(
            not bill.payment_attempts.filter(
                status__in=["creating", "pending", "unknown"]
            ).exists(),
            "unresolved_payment",
            "在线结果未决，请先查单",
        )
        record_funds(
            bill,
            reference_index=receipt.reference_index,
            amount_cents=receipt.amount_cents,
            received_at=receipt.paid_at,
            kind="offline",
            source_id=receipt.id,
        )
    receipt.status, receipt.reason = ("approved" if approved else "rejected"), reason
    receipt.reviewed_by, receipt.reviewed_at = actor.membership, timezone.now()
    advance(receipt, "status", "reason", "reviewed_by", "reviewed_at")
    audit(
        actor,
        bill,
        "bill.receipt_reviewed",
        reason=reason,
        receipt_id=str(receipt.id),
        status=receipt.status,
    )
    return receipt


def visible_partner_lines(actor):
    from .sales import visible_orders

    qs = PartnerBillLine.objects.select_related(
        "bill", "redemption__appointment__benefit__card__order", "redemption__appointment__clinic"
    )
    if actor.platform:
        return qs
    qs = qs.filter(bill__organization=actor.organization)
    if actor.membership.role == "admin":
        return qs
    if actor.organization.kind == "channel":
        return qs.filter(redemption__appointment__clinic__in=visible_clinics(actor))
    return qs.filter(redemption__appointment__benefit__card__order__in=visible_orders(actor))


def get_partner_bill(actor, bill_id, *, lock=False, operate=False):
    qs = PartnerBill.objects.all()
    if not actor.platform:
        qs = qs.filter(organization=actor.organization)
        if actor.membership.role != "admin":
            require(not operate, "forbidden", "业务员仅可查询本人逐笔明细，整单由管理员处理", 403)
            require(False, "forbidden", "请使用本人结算明细接口，不可读取整单", 403)
    if lock:
        qs = qs.select_for_update()
    bill = qs.filter(pk=bill_id).first()
    require(bill, "not_found", "合作方结算单不存在", 404)
    return bill


@transaction.atomic
def generate_partner_bills(*, issued_on):
    require(issued_on.day == 1, "not_issue_day", "合作方在每月1日出账")
    cutoff = timezone.make_aware(datetime.combine(issued_on, time.min))
    month = (issued_on - timedelta(days=1)).replace(day=1)
    result = []
    for kind in ["resource", "channel"]:
        candidates = Redemption.objects.filter(
            status="active", settled_at__lt=cutoff, created_at__lt=cutoff
        ).exclude(partner_lines__kind=kind)
        organizations = list(candidates.order_by().values_list(f"{kind}_id", flat=True).distinct())
        for org_id in sorted(organizations, key=str):
            advisory_lock("partner_bill", f"{org_id}:{month}")
            old = PartnerBill.objects.filter(organization_id=org_id, month=month).first()
            if old:
                result.append(old)
                continue
            records = list(
                candidates.select_for_update()
                .filter(**{f"{kind}_id": org_id})
                .order_by("created_at", "id")
            )
            if not records:
                continue
            total = sum(getattr(record, f"{kind}_cents") for record in records)
            bill = PartnerBill.objects.create(
                organization_id=org_id,
                month=month,
                issued_on=issued_on,
                due_at=due_at(issued_on, "monthly"),
                total_cents=total,
                status="pending_confirmation" if total else "no_payment",
            )
            PartnerBillLine.objects.bulk_create(
                [
                    PartnerBillLine(
                        bill=bill,
                        redemption=record,
                        kind=kind,
                        amount_cents=getattr(record, f"{kind}_cents"),
                    )
                    for record in records
                ]
            )
            audit(
                None,
                bill,
                "partner_bill.generated",
                total_cents=total,
                count=len(records),
                status=bill.status,
            )
            result.append(bill)
    return result


@transaction.atomic
def confirm_partner_bill(actor, bill_id, *, version, confirmed):
    bill = get_partner_bill(actor, bill_id, lock=True, operate=True)
    require(not actor.platform, "forbidden", "平台不能代合作方确认", 403)
    check_version(bill, version)
    require(
        confirmed is True and bill.status == "pending_confirmation" and bill.total_cents > 0,
        "invalid_state",
        "请核对待确认的正金额结算单",
        400,
    )
    bill.status, bill.confirmed_by, bill.confirmed_at = (
        "pending_payment",
        actor.membership,
        timezone.now(),
    )
    bill.confirmed_version = bill.version + 1
    advance(bill, "status", "confirmed_by", "confirmed_at", "confirmed_version")
    audit(actor, bill, "partner_bill.confirmed", total_cents=bill.total_cents)
    return bill


@transaction.atomic
def pay_partner_bill(
    actor, bill_id, *, version, amount_cents, paid_at, reference, attachment_ids, confirmed
):
    actor.require_platform()
    bill = get_partner_bill(actor, bill_id, lock=True, operate=True)
    check_version(bill, version)
    require(
        bill.status == "pending_payment"
        and bill.confirmed_version == bill.version
        and confirmed is True,
        "invalid_state",
        "仅合作方已确认的当前版本可登记实际付款",
    )
    require(
        type(amount_cents) is int and amount_cents == bill.total_cents and amount_cents > 0,
        "invalid_amount",
        "须登记整单全额付款",
        400,
    )
    require(
        isinstance(paid_at, datetime)
        and timezone.is_aware(paid_at)
        and paid_at <= timezone.now()
        and isinstance(reference, str)
        and reference.strip(),
        "payment_required",
        "请填写实际付款时间和流水号",
        400,
    )
    validate_attachment_ids(actor, attachment_ids, purposes={"payment"})
    reference_index = digest(reference.strip(), purpose="partner_payment")
    advisory_lock("partner_payment", reference_index)
    require(
        not PartnerPayment.objects.filter(reference_index=reference_index).exists(),
        "duplicate_payment",
        "此付款流水已登记",
    )
    payment = PartnerPayment.objects.create(
        bill=bill,
        amount_cents=amount_cents,
        bill_version=bill.version,
        paid_at=paid_at,
        reference=reference,
        reference_index=reference_index,
        attachment_ids=attachment_ids,
        actor=actor.membership,
    )
    link_files(attachment_ids, bill)
    bill.status = "pending_receipt"
    advance(bill, "status")
    audit(actor, bill, "partner_bill.paid", payment_id=str(payment.id), amount_cents=amount_cents)
    return bill


@transaction.atomic
def receive_partner_bill(actor, bill_id, *, version, actual_received_on, confirmed):
    bill = get_partner_bill(actor, bill_id, lock=True, operate=True)
    require(not actor.platform, "forbidden", "平台不能代合作方确认收款", 403)
    check_version(bill, version)
    require(
        bill.status == "pending_receipt" and confirmed is True,
        "invalid_state",
        "请核对已实际全额到账的付款记录",
    )
    payment = PartnerPayment.objects.get(bill=bill)
    require(
        payment.amount_cents == bill.total_cents and payment.bill_version == bill.confirmed_version,
        "payment_mismatch",
        "付款金额或版本不一致，请反馈异常",
    )
    require(
        timezone.localtime(payment.paid_at).date() <= actual_received_on <= timezone.localdate(),
        "invalid_received_date",
        "实际到账日期不合法",
        400,
    )
    validate_attachment_ids(actor, payment.attachment_ids, purposes={"payment"})
    bill.status, bill.received_by, bill.received_at, bill.actual_received_on = (
        "completed",
        actor.membership,
        timezone.now(),
        actual_received_on,
    )
    advance(bill, "status", "received_by", "received_at", "actual_received_on")
    bill.feedback.filter(status="open").update(status="closed")
    audit(actor, bill, "partner_bill.received", payment_id=str(payment.id))
    return bill


@transaction.atomic
def submit_feedback(actor, bill_id, *, partner, message, version):
    actor.require_admin()
    require(not actor.platform, "forbidden", "平台通过回复处理对账反馈", 403)
    bill = (
        get_partner_bill(actor, bill_id, lock=True, operate=True)
        if partner
        else get_bill(actor, bill_id, lock=True, pay=True)
    )
    check_version(bill, version)
    require(
        bill.status not in {"completed", "settled", "cancelled", "no_payment"},
        "invalid_state",
        "已结束的账单不再新增对账反馈",
    )
    require(
        isinstance(message, str) and 1 <= len(message.strip()) <= 2000,
        "message_required",
        "请填写对账反馈，最多2000字",
        400,
    )
    require(
        not bill.feedback.filter(status="open").exists(),
        "feedback_pending",
        "已有待处理反馈，请等待平台回复",
    )
    feedback = FinanceFeedback.objects.create(
        **{"partner_bill" if partner else "clinic_bill": bill},
        kind="reconciliation",
        message=message.strip(),
        actor=actor.membership,
    )
    if not partner:
        # Feedback never changes the statement amount, issue date or payment deadline.
        bill.dispute = True
        bill.save(update_fields=["dispute", "updated_at"])
    audit(actor, bill, "bill.feedback_submitted", feedback_id=str(feedback.id))
    return feedback


@transaction.atomic
def respond_feedback(actor, feedback_id, *, response, version):
    actor.require_platform()
    ref = FinanceFeedback.objects.filter(pk=feedback_id).first()
    require(ref, "not_found", "反馈不存在", 404)
    bill = (
        get_partner_bill(actor, ref.partner_bill_id, lock=True)
        if ref.partner_bill_id
        else get_bill(actor, ref.clinic_bill_id, lock=True)
    )
    feedback = FinanceFeedback.objects.select_for_update().get(pk=feedback_id)
    check_version(feedback, version)
    require(feedback.status == "open", "invalid_state", "反馈已处理")
    require(
        isinstance(response, str) and 1 <= len(response.strip()) <= 2000,
        "response_required",
        "请填写处理结果，最多2000字",
        400,
    )
    feedback.response, feedback.status = response.strip(), "closed"
    feedback.responded_by, feedback.responded_at = actor.membership, timezone.now()
    advance(feedback, "response", "status", "responded_by", "responded_at")
    if feedback.clinic_bill_id:
        bill.dispute = bill.feedback.filter(status="open").exists()
        bill.save(update_fields=["dispute", "updated_at"])
    audit(actor, bill, "bill.feedback_responded", feedback_id=str(feedback.id))
    return feedback
