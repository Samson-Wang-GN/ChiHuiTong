from datetime import datetime, timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from chihuitong.crypto import digest
from chihuitong.errors import require
from chihuitong.models import Appointment, Benefit, Card, Clinic, ClinicBill, ClinicBillLine, ClinicProduct, Customer, CustomerMessage, FulfillmentTask, Outbox, Product, Redemption, Reschedule, SalesOrder

from .clinics import assert_new_business, visible_clinics
from .common import advance, audit, check_version
from .contracts import resolve_fees
from .customers import event
from .sales import visible_orders


def visible_appointments(actor):
    qs = Appointment.objects.select_related("clinic", "benefit__card__order", "customer")
    if actor.platform:
        return qs
    if actor.organization.kind in {"clinic", "channel"}:
        return qs.filter(clinic__in=visible_clinics(actor))
    return qs.filter(benefit__card__order__in=visible_orders(actor))


def clinic_actor(actor, appointment):
    require(actor.organization.kind == "clinic" and actor.organization.id == appointment.clinic.organization_id, "forbidden", "只有预约所属门诊员工可以处理履约", 403)


def customer_actor(customer_id, appointment):
    require(str(appointment.customer_id) == str(customer_id), "not_found", "预约不存在", 404)


def validate_date(when, benefit, *, future=False):
    require(isinstance(when, datetime) and timezone.is_aware(when), "invalid_time", "请填写有效预约日期和时间", 400)
    require(benefit.activated_at and benefit.expires_at, "benefit_unclaimed", "请先领取或激活权益")
    date = timezone.localtime(when).date()
    require(timezone.localtime(benefit.activated_at).date() <= date <= timezone.localtime(benefit.expires_at).date(), "benefit_expired", "预约日期不能超过权益有效期")
    if future:
        require(when > timezone.now(), "past_appointment", "请选择未来的预约时间", 400)


def locked_appointment(appointment_id):
    reference = Appointment.objects.filter(pk=appointment_id).values("benefit_id", "benefit__card_id", "benefit__card__order_id", "clinic_id").first()
    require(reference, "not_found", "预约不存在", 404)
    SalesOrder.objects.select_for_update().get(pk=reference["benefit__card__order_id"])
    Card.objects.select_for_update().get(pk=reference["benefit__card_id"])
    clinic = Clinic.objects.select_for_update().select_related("organization", "channel").get(pk=reference["clinic_id"])
    appointment = Appointment.objects.select_for_update().get(pk=appointment_id)
    benefit = Benefit.objects.select_for_update().select_related("card__order", "product").get(pk=reference["benefit_id"])
    appointment.clinic, appointment.benefit = clinic, benefit
    return appointment, benefit


def notify_clinic(appointment, kind):
    Outbox.objects.get_or_create(kind="sms.business", dedup_key=f"{kind}:{appointment.id}:{appointment.version}", defaults={"payload": {"template": kind, "appointment_id": str(appointment.id), "phone": appointment.clinic.profile["frontdesk_phone"]}, "available_at": timezone.now()})


def close_tasks(appointment, reason):
    appointment.fulfillment_tasks.exclude(status="closed").update(status="closed", closed_at=timezone.now(), close_reason=reason)


def resolve_messages(appointment):
    CustomerMessage.objects.filter(appointment=appointment, status="pending").update(status="resolved", resolved_at=timezone.now())


def message(appointment, kind):
    CustomerMessage.objects.get_or_create(customer_id=appointment.customer_id, appointment=appointment, kind=kind, round=appointment.restoration_round)


def appointment_event(appointment):
    event(appointment.benefit.card, "appointment.state", obj=appointment, status=appointment.status, customer_id=str(appointment.customer_id), completion_source=appointment.completion_source)


@transaction.atomic
def book(customer_id, *, benefit_id, clinic_id, requested_at):
    ref = Benefit.objects.filter(pk=benefit_id, customer_id=customer_id).values("card_id", "card__order_id").first()
    require(ref, "not_found", "权益不存在", 404)
    SalesOrder.objects.select_for_update().get(pk=ref["card__order_id"])
    card = Card.objects.select_for_update().get(pk=ref["card_id"])
    clinic = Clinic.objects.select_for_update().select_related("organization", "channel").filter(pk=clinic_id).first()
    require(clinic, "not_found", "门诊不存在", 404)
    benefit = Benefit.objects.select_for_update().select_related("card__order").get(pk=benefit_id)
    require(Customer.objects.filter(pk=customer_id, registered_at__isnull=False).exists(), "customer_unbound", "请先授权手机号登录", 403)
    require(not card.frozen and card.activated_at and card.status == "active", "benefit_unavailable", "权益尚未激活、已失效或被冻结")
    validate_date(requested_at, benefit, future=True)
    assert_new_business(clinic, benefit.product_id)
    require(clinic.service_status == "online" and ClinicProduct.objects.filter(clinic=clinic, product_id=benefit.product_id, status="online").exists(), "clinic_offline", "门诊或该推广产品暂不接受新预约")
    units = benefit.card.order.product_snapshot["redemption_units"]
    require(benefit.available >= units, "insufficient_benefit", "可用权益份数不足")
    benefit.available -= units
    benefit.reserved += units
    advance(benefit, "available", "reserved")
    appointment = Appointment.objects.create(customer_id=customer_id, benefit=benefit, clinic=clinic, booked_channel=clinic.channel, requested_at=requested_at, pending_deadline=timezone.now() + timedelta(hours=clinic.confirmation_hours), units=units)
    appointment_event(appointment)
    notify_clinic(appointment, "appointment.new")
    return appointment


@transaction.atomic
def confirm(actor, appointment_id, *, scheduled_at, version):
    appointment, benefit = locked_appointment(appointment_id)
    clinic_actor(actor, appointment)
    check_version(appointment, version)
    require(appointment.status == "pending" and timezone.now() < appointment.pending_deadline, "invalid_state", "预约已处理或超过待确认时限")
    validate_date(scheduled_at, benefit, future=True)
    appointment.status, appointment.scheduled_at = "success", scheduled_at
    advance(appointment, "status", "scheduled_at")
    audit(actor, appointment, "appointment.confirmed")
    appointment_event(appointment)
    return appointment


def release_reservation(appointment, benefit):
    require(appointment.reserved and benefit.reserved >= appointment.units, "reservation_missing", "原预约权益占用不存在，请核对")
    benefit.reserved -= appointment.units
    benefit.available += appointment.units
    appointment.reserved = False
    advance(benefit, "reserved", "available")


@transaction.atomic
def cancel(appointment_id, *, version, reason, actor=None, customer_id=None):
    appointment, benefit = locked_appointment(appointment_id)
    if actor:
        clinic_actor(actor, appointment)
    else:
        customer_actor(customer_id, appointment)
    check_version(appointment, version)
    require(reason.strip() and appointment.status in {"pending", "success"}, "invalid_state", "请填写取消原因，当前预约须未完成或取消")
    require(appointment.status != "success" or timezone.now() < appointment.scheduled_at, "overdue_feedback_required", "预约时间已过，请使用过期预约处理，不可直接释放权益")
    require(not appointment.patient_arrived_at and not appointment.conflict, "feedback_conflict", "存在到诊反馈，请先核对")
    release_reservation(appointment, benefit)
    appointment.status, appointment.cancellation_reason = "cancelled", reason
    advance(appointment, "status", "cancellation_reason", "reserved")
    appointment.reschedules.filter(status="pending").update(status="cancelled")
    close_tasks(appointment, "cancelled")
    resolve_messages(appointment)
    audit(actor, appointment, "appointment.cancelled", reason=reason)
    appointment_event(appointment)
    notify_clinic(appointment, "appointment.cancelled")
    return appointment


@transaction.atomic
def reschedule(appointment_id, *, proposed_at, version, actor=None, customer_id=None, agreed=False):
    appointment, benefit = locked_appointment(appointment_id)
    if actor:
        clinic_actor(actor, appointment)
        require(agreed is True, "agreement_required", "请确认已与客户协商一致", 400)
    else:
        customer_actor(customer_id, appointment)
    check_version(appointment, version)
    require(appointment.status == "success" and not appointment.conflict and not appointment.patient_arrived_at, "invalid_state", "当前预约不能改期")
    require(not appointment.reschedules.filter(status="pending").exists(), "pending_reschedule", "已有待处理改期申请")
    validate_date(proposed_at, benefit, future=True)
    require(proposed_at != appointment.scheduled_at, "same_time", "改期时间没有变化", 400)
    change = Reschedule.objects.create(appointment=appointment, previous_at=appointment.scheduled_at, proposed_at=proposed_at, initiated_by="clinic" if actor else "customer", actor=actor.membership if actor else None, status="approved" if actor else "pending", agreed=bool(actor), expires_at=timezone.now() + timedelta(hours=24))
    if actor:
        appointment.scheduled_at = proposed_at
        appointment.schedule_revision += 1
        close_tasks(appointment, "rescheduled")
    advance(appointment, "scheduled_at", "schedule_revision")
    audit(actor, appointment, "appointment.reschedule_created", change_id=str(change.id), initiator=change.initiated_by)
    if not actor:
        notify_clinic(appointment, "appointment.reschedule")
    return change


@transaction.atomic
def review_reschedule(actor, change_id, *, approved, version, reason):
    ref = Reschedule.objects.filter(pk=change_id).first()
    require(ref, "not_found", "改期申请不存在", 404)
    appointment, benefit = locked_appointment(ref.appointment_id)
    clinic_actor(actor, appointment)
    change = Reschedule.objects.select_for_update().get(pk=change_id)
    check_version(change, version)
    require(change.status == "pending" and appointment.status == "success" and timezone.now() < change.expires_at, "invalid_state", "改期申请已处理或超时")
    require(type(approved) is bool and reason.strip(), "reason_required", "请填写改期处理意见", 400)
    if approved:
        validate_date(change.proposed_at, benefit, future=True)
        appointment.scheduled_at = change.proposed_at
        appointment.schedule_revision += 1
        advance(appointment, "scheduled_at", "schedule_revision")
        close_tasks(appointment, "rescheduled")
    change.status, change.reason = ("approved" if approved else "rejected"), reason
    change.reviewed_by, change.reviewed_at = actor.membership, timezone.now()
    advance(change, "status", "reason", "reviewed_by", "reviewed_at")
    audit(actor, appointment, "appointment.reschedule_reviewed", reason=reason, change_id=str(change.id), status=change.status)
    return change


@transaction.atomic
def report_absent(actor, appointment_id, *, version, confirmed):
    appointment, _ = locked_appointment(appointment_id)
    clinic_actor(actor, appointment)
    check_version(appointment, version)
    require(confirmed is True, "confirmation_required", "请确认取消预约但保留权益占用，客户须自行申请恢复", 400)
    require(appointment.status == "success" and appointment.scheduled_at < timezone.now(), "invalid_state", "仅已过预约时间的成功预约可反馈患者未到")
    require(not appointment.patient_arrived_at and not appointment.conflict and not appointment.reschedules.filter(status="pending").exists(), "feedback_conflict", "存在到诊反馈、冲突或未决改期，不能直接报未到")
    appointment.status, appointment.clinic_absent_at, appointment.cancellation_reason = "cancelled", timezone.now(), "门诊反馈患者未到，权益仍占用"
    advance(appointment, "status", "clinic_absent_at", "cancellation_reason")
    close_tasks(appointment, "clinic_absent")
    message(appointment, "attendance_confirmation")
    audit(actor, appointment, "appointment.clinic_absent")
    appointment_event(appointment)
    return appointment


@transaction.atomic
def customer_feedback(customer_id, appointment_id, *, arrived, version, confirmed):
    appointment, benefit = locked_appointment(appointment_id)
    customer_actor(customer_id, appointment)
    check_version(appointment, version)
    require(type(arrived) is bool and confirmed is True, "confirmation_required", "请确认实际到诊情况", 400)
    require((appointment.completion_source == "system" or appointment.clinic_absent_at) and appointment.reserved and not appointment.restoration_pending, "invalid_state", "此预约不支持到诊确认")
    require(not appointment.redemptions.filter(status="active").exists(), "already_redeemed", "该预约已核销")
    require(not appointment.reschedules.filter(status="pending").exists(), "pending_reschedule", "存在未决改期，请先处理")
    if arrived:
        appointment.patient_arrived_at = appointment.patient_arrived_at or timezone.now()
        appointment.conflict = bool(appointment.clinic_absent_at)
        advance(appointment, "patient_arrived_at", "conflict")
        FulfillmentTask.objects.get_or_create(appointment=appointment, kind="supplement", round=appointment.schedule_revision, defaults={"status": "conflict" if appointment.conflict else "pending"})
        resolve_messages(appointment)
        notify_clinic(appointment, "appointment.supplement")
    else:
        require(not appointment.patient_arrived_at and not appointment.conflict, "feedback_conflict", "已存在到诊反馈或冲突，不能自动恢复")
        release_reservation(appointment, benefit)
        appointment.status, appointment.cancellation_reason = "cancelled", "客户声明未到诊，已解除权益占用"
        advance(appointment, "status", "cancellation_reason", "reserved")
        close_tasks(appointment, "customer_restored")
        resolve_messages(appointment)
        appointment_event(appointment)
        notify_clinic(appointment, "appointment.restored")
    audit(None, appointment, "appointment.customer_feedback", customer_id=str(customer_id), arrived=arrived, conflict=appointment.conflict)
    return appointment


def can_redeem(appointment, benefit):
    require(appointment.status == "success" or (appointment.status == "completed" and appointment.completion_source == "system"), "invalid_state", "预约未确认、已取消或已核销")
    require(not appointment.restoration_pending and appointment.reserved and benefit.reserved >= appointment.units, "reservation_missing", "此预约权益已释放或处于待恢复，不能核销")
    require(not benefit.card.frozen and not appointment.conflict and not appointment.reschedules.filter(status="pending").exists(), "redemption_blocked", "存在冻结、冲突或待处理改期，不能核销")
    require(appointment.scheduled_at <= timezone.now(), "service_not_due", "尚未到预约时间，不能确认治疗已完成")
    validate_date(appointment.scheduled_at, benefit)


@transaction.atomic
def redeem(actor, appointment_id, *, credential, confirmed, version):
    appointment, benefit = locked_appointment(appointment_id)
    clinic_actor(actor, appointment)
    existing = appointment.redemptions.filter(status="active").first()
    require(isinstance(credential, str) and digest(credential, purpose="card") == benefit.card.credential_digest, "invalid_credential", "二维码与当前预约权益不一致", 400)
    if existing:
        return existing
    check_version(appointment, version)
    require(confirmed is True, "service_confirmation", "请确认客户已完成本次服务", 400)
    can_redeem(appointment, benefit)
    product = Product.objects.select_for_update().get(pk=benefit.product_id)
    snapshot = resolve_fees(benefit.source.organization_id, appointment.clinic, product)
    snapshot.update({"internal_name": product.internal_name, "external_name": benefit.card.order.product_snapshot["external_name"], "scheduled_at": appointment.scheduled_at.isoformat()})
    record = Redemption.objects.create(appointment=appointment, actor=actor.membership, resource_id=benefit.source.organization_id, channel_id=appointment.clinic.channel_id, units=appointment.units, previous_completion_source=appointment.completion_source, snapshot=snapshot, **{key: snapshot[key] for key in ["fee_cents", "resource_cents", "channel_cents", "platform_cents"]})
    benefit.reserved -= appointment.units
    benefit.used += appointment.units
    advance(benefit, "reserved", "used")
    appointment.status, appointment.completion_source, appointment.completed_at, appointment.reserved = "completed", "clinic", timezone.now(), False
    advance(appointment, "status", "completion_source", "completed_at", "reserved")
    close_tasks(appointment, "redeemed")
    resolve_messages(appointment)
    audit(actor, appointment, "appointment.redeemed", redemption_id=str(record.id), fee_cents=record.fee_cents)
    event(benefit.card, "redemption.active", obj=record, customer_id=str(appointment.customer_id), units=record.units)
    appointment_event(appointment)
    return record


@transaction.atomic
def reverse_redemption(actor, redemption_id, *, version, reason):
    reference = Redemption.objects.filter(pk=redemption_id).first()
    require(reference, "not_found", "核销记录不存在", 404)
    appointment, benefit = locked_appointment(reference.appointment_id)
    clinic_actor(actor, appointment)
    line = ClinicBillLine.objects.filter(redemption_id=redemption_id, active=True).first()
    bill = ClinicBill.objects.select_for_update().get(pk=line.bill_id) if line else None
    record = Redemption.objects.select_for_update().get(pk=redemption_id)
    if record.status == "reversed":
        return record
    check_version(record, version)
    require(reason.strip(), "reason_required", "请填写错误核销撤销原因", 400)
    require(record.settled_at is None and (not bill or bill.status != "settled"), "already_settled", "账单已结清，不能撤销核销")
    if bill:
        require(not bill.receipts.filter(status="pending").exists() and not bill.payment_attempts.filter(status__in=["creating", "pending", "unknown"]).exists(), "unresolved_payment", "存在未决支付或待审收款，请先核实")
        # A prior partial receipt cannot be silently turned into excess money by reversal.
        require(bill.received_cents <= bill.total_cents - record.fee_cents, "refund_review_required", "撤销将使已收款超过应收，请先由平台核对，暂不能自动撤销")
        line.active, line.removed_at = False, timezone.now()
        advance(line, "active", "removed_at")
        bill.total_cents -= record.fee_cents
        if bill.total_cents == 0:
            bill.status = "cancelled"
        from .finance import settle_if_full, snapshot_bill
        settle_if_full(bill)
        advance(bill, "total_cents", "status", "settled_at")
        snapshot_bill(bill)
        audit(actor, bill, "bill.redemption_removed", reason=reason, redemption_id=str(record.id), total_cents=bill.total_cents)
    record.status, record.reversed_at, record.reversed_by, record.reversal_reason = "reversed", timezone.now(), actor.membership, reason
    advance(record, "status", "reversed_at", "reversed_by", "reversal_reason")
    benefit.used -= appointment.units
    if record.previous_completion_source == "system":
        benefit.restoring += appointment.units
        appointment.status, appointment.completion_source = "completed", "system"
        appointment.restoration_pending = True
        appointment.restoration_round += 1
        close_tasks(appointment, "supplement_reversed")
        message(appointment, "reversal_restoration")
    else:
        benefit.reserved += appointment.units
        appointment.status, appointment.completion_source, appointment.reserved = "success", "", True
        appointment.completed_at = None
    advance(benefit, "used", "reserved", "restoring")
    advance(appointment, "status", "completion_source", "reserved", "completed_at", "restoration_pending", "restoration_round")
    audit(actor, appointment, "appointment.redemption_reversed", reason=reason, redemption_id=str(record.id))
    event(benefit.card, "redemption.reversed", obj=record, customer_id=str(appointment.customer_id), units=record.units)
    appointment_event(appointment)
    return record


@transaction.atomic
def restore_reversal(customer_id, appointment_id, *, version, confirmed):
    appointment, benefit = locked_appointment(appointment_id)
    customer_actor(customer_id, appointment)
    check_version(appointment, version)
    require(confirmed is True, "confirmation_required", "请确认申请恢复本次撤销的权益", 400)
    require(appointment.restoration_pending and benefit.restoring >= appointment.units and not appointment.redemptions.filter(status="active").exists(), "restoration_unavailable", "没有待恢复的撤销权益")
    benefit.restoring -= appointment.units
    benefit.available += appointment.units
    advance(benefit, "restoring", "available")
    appointment.restoration_pending, appointment.status, appointment.cancellation_reason = False, "cancelled", "客户申请恢复补核销撤销权益"
    advance(appointment, "restoration_pending", "status", "cancellation_reason")
    resolve_messages(appointment)
    appointment_event(appointment)
    audit(None, appointment, "appointment.reversal_restored", customer_id=str(customer_id), round=appointment.restoration_round)
    return appointment


@transaction.atomic
def process_deadline(appointment_id, *, now=None):
    now = now or timezone.now()
    appointment, benefit = locked_appointment(appointment_id)
    appointment.reschedules.filter(status="pending", expires_at__lte=now).update(status="expired", reviewed_at=now)
    if appointment.status == "pending" and now >= appointment.pending_deadline:
        release_reservation(appointment, benefit)
        appointment.status, appointment.cancellation_reason = "cancelled", "门诊待确认超时"
        advance(appointment, "status", "cancellation_reason", "reserved")
        appointment_event(appointment)
        audit(None, appointment, "appointment.pending_expired")
    elif appointment.status == "success" and now >= appointment.scheduled_at + timedelta(hours=24):
        blocked = appointment.patient_arrived_at or appointment.conflict or appointment.reschedules.filter(status="pending").exists()
        if now >= appointment.scheduled_at + timedelta(hours=72) and not blocked:
            appointment.status, appointment.completion_source, appointment.completed_at = "completed", "system", now
            advance(appointment, "status", "completion_source", "completed_at")
            close_tasks(appointment, "system_completed")
            message(appointment, "attendance_confirmation")
            appointment_event(appointment)
            audit(None, appointment, "appointment.system_completed")
        else:
            _, created = FulfillmentTask.objects.get_or_create(appointment=appointment, kind="overdue", round=appointment.schedule_revision)
            if created:
                notify_clinic(appointment, "appointment.overdue")
    return appointment
