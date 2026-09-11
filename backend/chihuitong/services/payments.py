import hashlib
import json
import uuid
from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from chihuitong.crypto import digest
from chihuitong.errors import BusinessError, require
from chihuitong.integrations.wechat_pay import WeChatPay
from chihuitong.models import ClinicBill, Outbox, PaymentAttempt, PaymentNotification

from .common import advance, advisory_lock, audit, check_version
from .finance import get_bill, record_funds


def get_attempt(actor, attempt_id, *, operate=False):
    ref = PaymentAttempt.objects.filter(pk=attempt_id).first()
    require(ref, "not_found", "支付记录不存在", 404)
    get_bill(actor, ref.bill_id, pay=operate and not actor.platform)
    return ref


def projection(attempt):
    data = {
        "id": str(attempt.id),
        "bill_id": str(attempt.bill_id),
        "number": attempt.number,
        "status": attempt.status,
        "amount_cents": attempt.amount_cents,
        "method": attempt.method,
        "bill_version": attempt.bill_version,
        "version": attempt.version,
        "expires_at": attempt.expires_at.isoformat() if attempt.expires_at else None,
        "error_code": attempt.error_code,
    }
    if attempt.status == "pending" and attempt.expires_at and attempt.expires_at > timezone.now():
        data["payment_parameters"] = attempt.gateway_payload
    return data


def enqueue_reconciliation(attempt):
    Outbox.objects.get_or_create(
        kind="payment.reconcile",
        dedup_key=f"payment:{attempt.id}",
        defaults={
            "payload": {"attempt_id": str(attempt.id)},
            "available_at": timezone.now() + timedelta(seconds=30),
        },
    )


def create_payment(
    actor, bill_id, *, version, method, key, verified_openid=None, verified_appid=None
):
    # Do not wrap this whole method in API idempotent(): outbound calls must not hold bill locks.
    require(
        isinstance(key, str) and 8 <= len(key) <= 128, "idempotency_key", "请提供幂等请求编号", 400
    )
    require(method in {"native", "jsapi"}, "invalid_method", "请选择扫码或小程序支付", 400)
    gateway = WeChatPay()
    if method == "jsapi":
        require(
            verified_openid and verified_appid == gateway.config.appid,
            "openid_required",
            "请从门诊小程序授权身份发起支付",
            403,
        )
    with transaction.atomic():
        bill = get_bill(actor, bill_id, lock=True, pay=True)
        advisory_lock("payment_request", f"{actor.membership.id}:{key}")
        old = PaymentAttempt.objects.filter(created_by=actor.membership, request_key=key).first()
        if old:
            require(
                old.bill_id == bill.id and old.bill_version == version and old.method == method,
                "idempotency_conflict",
                "同一请求编号不可用于其他付款",
            )
            return old
        check_version(bill, version)
        require(
            bill.status == "open" and bill.total_cents > bill.received_cents,
            "invalid_state",
            "账单没有待付金额",
        )
        require(
            not bill.receipts.filter(status="pending").exists(),
            "receipt_pending",
            "请先处理已提交付款凭证",
        )
        old = bill.payment_attempts.filter(status__in=["creating", "pending", "unknown"]).first()
        if old:
            require(old.method == method, "unresolved_payment", "请先查单或关闭原支付，再切换方式")
            return old
        attempt = PaymentAttempt.objects.create(
            bill=bill,
            bill_version=bill.version,
            number=uuid.uuid4().hex,
            amount_cents=bill.total_cents - bill.received_cents,
            method=method,
            created_by=actor.membership,
            appid=gateway.config.appid,
            mchid=gateway.config.mchid,
            request_key=key,
            expires_at=timezone.now() + timedelta(minutes=15),
        )
        enqueue_reconciliation(attempt)
        audit(
            actor,
            bill,
            "payment.created",
            attempt_id=str(attempt.id),
            amount_cents=attempt.amount_cents,
        )
    try:
        result = gateway.create(attempt, openid=verified_openid)
        if method == "jsapi":
            result = gateway.client_parameters(result["prepay_id"])
    except BusinessError as exc:
        with transaction.atomic():
            current = PaymentAttempt.objects.select_for_update().get(pk=attempt.id)
            if current.status == "creating":
                current.status, current.error_code = "unknown", exc.code
                advance(current, "status", "error_code")
        return PaymentAttempt.objects.get(pk=attempt.id)
    with transaction.atomic():
        current = PaymentAttempt.objects.select_for_update().get(pk=attempt.id)
        # A callback may arrive before create returns. Never downgrade an observed success.
        if current.status == "creating":
            current.status, current.gateway_payload = "pending", result
            advance(current, "status", "gateway_payload")
    return current


def validate_observation(attempt, data):
    require(
        isinstance(data, dict)
        and data.get("appid") == attempt.appid
        and data.get("mchid") == attempt.mchid
        and data.get("out_trade_no") == attempt.number,
        "payment_identity_mismatch",
        "支付主体或订单不匹配",
        400,
    )
    amount = data.get("amount")
    require(
        isinstance(amount, dict)
        and type(amount.get("total")) is int
        and amount["total"] == attempt.amount_cents
        and amount.get("currency") == "CNY",
        "payment_amount_mismatch",
        "支付金额或币种不匹配",
        400,
    )
    state = data.get("trade_state")
    require(
        state in {"SUCCESS", "NOTPAY", "CLOSED", "REFUND", "USERPAYING", "PAYERROR", "REVOKED"},
        "payment_unknown_state",
        "支付状态不合法",
        400,
    )
    if state == "SUCCESS":
        require(
            data.get("trade_type") == ("NATIVE" if attempt.method == "native" else "JSAPI")
            and isinstance(data.get("transaction_id"), str)
            and 1 <= len(data["transaction_id"]) <= 100,
            "payment_identity_mismatch",
            "支付类型或流水不合法",
            400,
        )
        try:
            paid_at = datetime.fromisoformat(data["success_time"])
            require(
                timezone.is_aware(paid_at) and paid_at <= timezone.now() + timedelta(minutes=5),
                "payment_time_mismatch",
                "支付时间不合法",
                400,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise BusinessError("payment_time_mismatch", "支付时间不合法", 400) from exc
    return state


def payment_fields(data):
    # Drop payer OpenID, bank information, promotions and any incidental personal fields.
    return {
        key: data[key]
        for key in [
            "appid",
            "mchid",
            "out_trade_no",
            "amount",
            "trade_state",
            "trade_type",
            "transaction_id",
            "success_time",
        ]
        if key in data
    }


@transaction.atomic
def observe(attempt_id, data):
    ref = PaymentAttempt.objects.get(pk=attempt_id)
    bill = ClinicBill.objects.select_for_update().get(pk=ref.bill_id)
    attempt = PaymentAttempt.objects.select_for_update().get(pk=attempt_id)
    state = validate_observation(attempt, data)
    if state == "SUCCESS":
        require(
            not attempt.gateway_transaction
            or attempt.gateway_transaction == data["transaction_id"],
            "payment_transaction_mismatch",
            "同一支付订单出现不同流水，请核对",
        )
        ledger = record_funds(
            bill,
            reference_index=digest(
                attempt.mchid + ":" + data["transaction_id"], purpose="wechat_receipt"
            ),
            amount_cents=attempt.amount_cents,
            received_at=datetime.fromisoformat(data["success_time"]),
            kind="wechat",
            source_id=attempt.id,
            force_anomaly="bill_version_changed"
            if bill.version != attempt.bill_version and attempt.status != "success"
            else "",
        )
        attempt.status, attempt.gateway_transaction = "success", data["transaction_id"]
        attempt.error_code = ledger.anomaly
        attempt.gateway_payload = {}
        advance(attempt, "status", "gateway_transaction", "error_code", "gateway_payload")
        audit(
            None,
            bill,
            "payment.observed",
            attempt_id=str(attempt.id),
            amount_cents=attempt.amount_cents,
            anomaly=ledger.anomaly,
        )
    elif attempt.status == "success":
        if state == "REFUND":
            attempt.error_code = "external_refund_review"
            advance(attempt, "error_code")
            audit(None, bill, "payment.external_refund_detected", attempt_id=str(attempt.id))
    elif state == "CLOSED":
        attempt.status, attempt.gateway_payload = "closed", {}
        advance(attempt, "status", "gateway_payload")
        audit(None, bill, "payment.closed", attempt_id=str(attempt.id))
    else:
        # NOTPAY is not a closure. Network expiry alone never releases a pending payment.
        attempt.status = "pending" if state == "NOTPAY" else "unknown"
        attempt.error_code = "" if state == "NOTPAY" else "gateway_" + state.lower()
        advance(attempt, "status", "error_code")
    return attempt


def reconcile(attempt_id, *, close=False):
    attempt = PaymentAttempt.objects.get(pk=attempt_id)
    gateway = WeChatPay()
    require(
        attempt.appid == gateway.config.appid and attempt.mchid == gateway.config.mchid,
        "payment_config_changed",
        "商户配置已改变，请核对原收款主体",
        503,
    )
    data = gateway.query(attempt.number)
    state = validate_observation(attempt, data)
    if state == "NOTPAY" and (
        close or (attempt.expires_at and attempt.expires_at <= timezone.now())
    ):
        gateway.close(attempt.number)
        # Only the signed close response authorizes the local close; a concurrent success dominates.
        data = {**data, "trade_state": "CLOSED"}
    return observe(attempt.id, data)


def capture_notification(headers, raw):
    gateway = WeChatPay()
    notification_id, data = gateway.notification(headers, raw)
    attempt = PaymentAttempt.objects.filter(number=data.get("out_trade_no")).first()
    require(attempt, "payment_not_found", "未找到对应支付订单", 404)
    require(
        validate_observation(attempt, data) == "SUCCESS", "invalid_event", "非支付成功通知", 400
    )
    sanitized = payment_fields(data)
    fingerprint = hashlib.sha256(json.dumps(sanitized, sort_keys=True).encode()).hexdigest()
    with transaction.atomic():
        advisory_lock("payment_notification", notification_id)
        notice, created = PaymentNotification.objects.get_or_create(
            notification_id=notification_id,
            defaults={"attempt": attempt, "payload": sanitized, "body_digest": fingerprint},
        )
        require(
            notice.attempt_id == attempt.id and notice.body_digest == fingerprint,
            "payment_notification_conflict",
            "支付通知编号重复且内容不同",
            409,
        )
        if created:
            Outbox.objects.create(
                kind="payment.notification",
                dedup_key=notification_id,
                payload={"notification_id": str(notice.id)},
                available_at=timezone.now(),
            )
    return notice


@transaction.atomic
def process_notification(notification_id):
    # Observe locks bill before attempt. Notification lock is independent and never acquired by other flows.
    notice = PaymentNotification.objects.select_for_update().get(pk=notification_id)
    if notice.status == "done":
        return
    observe(notice.attempt_id, notice.payload)
    notice.status, notice.processed_at = "done", timezone.now()
    advance(notice, "status", "processed_at")
