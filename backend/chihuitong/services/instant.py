"""Pay-before-redemption, with durable funds independent of local completion."""

import uuid
from datetime import datetime, timedelta

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.utils import timezone

from chihuitong.crypto import digest
from chihuitong.errors import BusinessError, require
from chihuitong.models import InstantRedemptionOrder, Outbox, PaymentAttempt, Product, ReceiptLedger

from . import appointments, payments
from .common import Actor, advance, advisory_lock, audit, check_version
from .contracts import resolve_fees


def visible_orders(actor):
    from .clinics import visible_clinics

    qs = InstantRedemptionOrder.objects.select_related("appointment__clinic__organization", "cooperation__organization")
    if actor.platform:
        return qs
    if actor.organization.kind == "clinic":
        return qs.filter(appointment__clinic__organization=actor.organization)
    if actor.organization.kind == "channel":
        return qs.filter(appointment__clinic__in=visible_clinics(actor))
    return qs.none()


def get_order(actor, pk, *, operate=False):
    item = visible_orders(actor).filter(pk=pk).first()
    require(item, "not_found", "现付订单不存在或无权访问", 404)
    if operate:
        appointments.clinic_actor(actor, item.appointment)
    return item


def projection(item):
    return {
        "id": str(item.id), "appointment_id": str(item.appointment_id),
        "clinic_name": item.appointment.clinic.organization.name,
        "debtor_name": item.cooperation.organization.name, "status": item.status,
        "amount_cents": item.amount_cents, "version": item.version,
        "paid_at": item.paid_at, "created_at": item.created_at,
        "error_code": item.error_code, "redemption_id": str(item.redemption_id) if item.redemption_id else None,
        "internal_name": item.snapshot.get("internal_name", ""),
    }


def create(actor, appointment_id, *, credential, confirmed, version, quote, key):
    from .cooperations import assert_payment_ready

    assert_payment_ready()
    require(isinstance(key, str) and 8 <= len(key) <= 128, "idempotency_key", "请提供幂等请求编号", 400)
    gateway = payments.payment_gateway()
    with transaction.atomic():
        appointment, benefit = appointments.locked_appointment(appointment_id, allow_payment=True)
        appointments.clinic_actor(actor, appointment)
        advisory_lock("payment_request", f"{actor.membership.id}:{key}")
        old = PaymentAttempt.objects.filter(created_by=actor.membership, request_key=key).first()
        if old:
            require(old.instant_order_id and old.instant_order.appointment_id == appointment.id, "idempotency_conflict", "请求编号已用于其他付款")
            return old.instant_order
        existing = appointment.instant_orders.filter(status__in=["pending", "paid", "completed"]).first()
        if existing:
            return existing
        check_version(appointment, version)
        require(confirmed is True and digest(credential, purpose="card") == benefit.card.credential_digest, "service_confirmation", "请扫描客户二维码并确认已经完成本次服务", 400)
        appointments.can_redeem(appointment, benefit)
        product = Product.objects.select_for_update().get(pk=benefit.product_id)
        snapshot = resolve_fees(benefit.source.organization_id, appointment.clinic, product)
        require(snapshot.get("payment_mode") == "instant", "postpaid_clinic", "此门店采用账单后付，请直接确认核销")
        try:
            quoted = signing.loads(quote, salt="redemption-quote", max_age=300)
        except signing.BadSignature as exc:
            raise BusinessError("quote_expired", "费用确认已过期，请重新扫码", 409) from exc
        require(quoted == {"appointment_id": str(appointment.id), "version": appointment.version, "fee_cents": snapshot["fee_cents"], "fingerprint": appointments.fee_fingerprint(snapshot)}, "fee_changed", "费用已变化，请重新核对")
        snapshot.update(internal_name=product.internal_name, external_name=benefit.card.order.product_snapshot["external_name"], scheduled_at=appointment.scheduled_at.isoformat())
        order = InstantRedemptionOrder.objects.create(appointment=appointment, cooperation=appointment.clinic.cooperation, agreement_id=snapshot["clinic_contract_id"], created_by=actor.membership, amount_cents=snapshot["fee_cents"], snapshot=snapshot, appointment_version=appointment.version)
        require(order.amount_cents > 0, "invalid_instant_fee", "现付获客费必须大于零，请平台核对产品计费配置")
        attempt = PaymentAttempt.objects.create(instant_order=order, bill_version=order.version, number=uuid.uuid4().hex, amount_cents=order.amount_cents, method="native", created_by=actor.membership, appid=gateway.config.appid, mchid=gateway.config.mchid, request_key=key, preparation_started_at=timezone.now(), expires_at=timezone.now()+timedelta(minutes=15))
        payments.enqueue_reconciliation(attempt)
        audit(actor, order, "instant.created", amount_cents=order.amount_cents)
    prepare(attempt.id)
    return InstantRedemptionOrder.objects.get(pk=order.id)


def prepare(attempt_id):
    gateway = payments.payment_gateway()
    with transaction.atomic():
        attempt = PaymentAttempt.objects.select_for_update().get(pk=attempt_id)
        require(attempt.instant_order.status == "pending", "invalid_state", "此订单无需再次付款")
        if attempt.status in {"success", "closed"} or attempt.gateway_payload:
            return attempt
        require(attempt.appid == gateway.config.appid and attempt.mchid == gateway.config.mchid, "payment_config_changed", "收款配置已经改变，请核对原商户", 503)
        attempt.status = "creating"
        attempt.preparation_count += 1
        attempt.preparation_started_at = timezone.now()
        advance(attempt, "status", "preparation_count", "preparation_started_at")
    try:
        payload = gateway.create(attempt)
    except BusinessError as exc:
        PaymentAttempt.objects.filter(pk=attempt.id, status="creating", preparation_count=attempt.preparation_count).update(status="unknown", error_code=exc.code)
    else:
        PaymentAttempt.objects.filter(pk=attempt.id, status="creating", preparation_count=attempt.preparation_count).update(status="pending", gateway_payload=payload)
    if settings.ACCEPTANCE_SIMULATED_EXTERNALS:
        return payments.reconcile(attempt.id)
    return PaymentAttempt.objects.get(pk=attempt.id)


@transaction.atomic
def observe(attempt_id, data):
    ref = PaymentAttempt.objects.select_related("instant_order").get(pk=attempt_id)
    appointments.locked_appointment(ref.instant_order.appointment_id, allow_payment=True)
    order = InstantRedemptionOrder.objects.select_for_update().get(pk=ref.instant_order_id)
    attempt = PaymentAttempt.objects.select_for_update().get(pk=attempt_id)
    state = payments.validate_observation(attempt, data)
    if state == "SUCCESS":
        require(not attempt.gateway_transaction or attempt.gateway_transaction == data["transaction_id"], "payment_transaction_mismatch", "同一订单出现不同资金流水")
        if attempt.status != "success":
            reference = digest(attempt.mchid + ":" + data["transaction_id"], purpose="wechat_receipt")
            advisory_lock("receipt", reference)
            require(not ReceiptLedger.objects.filter(reference_index=reference).exists(), "duplicate_receipt", "资金流水已使用")
            order.paid_at = datetime.fromisoformat(data["success_time"])
            ReceiptLedger.objects.create(instant_order=order, reference_index=reference, source_id=attempt.id, amount_cents=attempt.amount_cents, received_at=order.paid_at, kind="wechat_simulated" if attempt.mchid == "SIMULATED-NO-MONEY" else "wechat")
            order.status = "paid"
            advance(order, "paid_at", "status")
            attempt.status, attempt.gateway_transaction, attempt.gateway_payload = "success", data["transaction_id"], {}
            advance(attempt, "status", "gateway_transaction", "gateway_payload")
            audit(None, order, "instant.paid", simulated=attempt.mchid == "SIMULATED-NO-MONEY", amount_cents=order.amount_cents)
        Outbox.objects.get_or_create(kind="instant.complete", dedup_key=f"instant:{order.id}", defaults={"payload": {"order_id": str(order.id)}})
        transaction.on_commit(lambda: try_complete(order.id))
    elif attempt.status == "success":
        if state == "REFUND":
            attempt.error_code = "external_refund_review"
            advance(attempt, "error_code")
    elif state == "CLOSED":
        attempt.status, attempt.gateway_payload = "closed", {}
        order.status = "closed"
        advance(attempt, "status", "gateway_payload")
        advance(order, "status")
        audit(None, order, "instant.closed")
    else:
        attempt.status = "pending" if state == "NOTPAY" else "unknown"
        advance(attempt, "status")
    return attempt


@transaction.atomic
def complete(order_id):
    ref = InstantRedemptionOrder.objects.get(pk=order_id)
    appointment, benefit = appointments.locked_appointment(ref.appointment_id, allow_payment=True)
    item = InstantRedemptionOrder.objects.select_for_update().select_related("created_by__organization", "created_by__account").get(pk=order_id)
    if item.status == "completed":
        return item
    require(item.status == "paid" and item.paid_at and item.receipts.exists(), "payment_pending", "尚未确认实际收款")
    check_version(appointment, item.appointment_version)
    appointments.can_redeem(appointment, benefit)
    require(not appointment.redemptions.filter(status="active").exists(), "redemption_conflict", "预约已有核销，请平台核对")
    item.redemption = appointments.finish_redemption(Actor(item.created_by), appointment, benefit, item.snapshot, settled_at=item.paid_at)
    item.status, item.error_code = "completed", ""
    advance(item, "redemption", "status", "error_code")
    audit(None, item, "instant.completed")
    return item


def try_complete(order_id):
    try:
        complete(order_id)
    except Exception as exc:
        # Funds already committed. Preserve the error and durable retry for operations.
        import logging

        code = exc.code if isinstance(exc, BusinessError) else type(exc).__name__
        InstantRedemptionOrder.objects.filter(pk=order_id, status="paid").update(error_code=code[:80])
        logging.getLogger("chihuitong.payments").warning("instant_completion_failed order=%s code=%s", order_id, code)
