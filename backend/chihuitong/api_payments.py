from django.conf import settings
from django.http import HttpResponse
from rest_framework import serializers
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .api import StrictSerializer, paginated, validated
from .api_catalog import VersionInput
from .errors import require
from .identity import rate_limit, request_actor
from .integrations.wechat_pay import MAX_MESSAGE
from .services import finance, payments


class PaymentInput(VersionInput):
    method = serializers.ChoiceField(choices=["native"])


@api_view(["GET"])
def payment_qr(request, attempt_id):
    import io

    import qrcode
    from django.utils import timezone

    actor = request_actor(request)
    attempt = payments.get_attempt(actor, attempt_id, operate=True)
    code = attempt.gateway_payload.get("code_url", "")
    require(
        attempt.status == "pending"
        and attempt.expires_at > timezone.now()
        and attempt.method == "native"
        and code.startswith("weixin://")
        and len(code) < 2048
        and attempt.mchid != "SIMULATED-NO-MONEY",
        "payment_not_available",
        "当前没有有效微信付款码，请查单核对",
        409,
    )
    output = io.BytesIO()
    qrcode.make(code).save(output, format="PNG")
    response = HttpResponse(output.getvalue(), content_type="image/png")
    response["Cache-Control"] = "no-store"
    return response


class InstantInput(VersionInput):
    credential = serializers.CharField(max_length=512)
    quote = serializers.CharField(max_length=2048)
    confirmed = serializers.BooleanField()


@api_view(["GET"])
def instant_orders(request):
    from .services import instant

    actor = request_actor(request)
    return paginated(
        request,
        instant.visible_orders(actor),
        instant.projection,
        states=["pending", "paid", "completed", "closed"],
    )


@api_view(["POST"])
def instant_create(request, appointment_id):
    from .services import instant

    actor = request_actor(request)
    item = instant.create(
        actor,
        appointment_id,
        **validated(InstantInput, request),
        key=request.headers.get("Idempotency-Key", ""),
    )
    return Response(instant.projection(item), status=201)


@api_view(["GET", "POST"])
def instant_detail(request, order_id):
    from .services import instant

    actor = request_actor(request)
    item = instant.get_order(
        actor, order_id, operate=request.method == "POST" and not actor.platform
    )
    if request.method == "POST":
        data = validated(PaymentActionInput, request)
        require(data["confirmed"], "confirmation_required", "请确认重新处理", 400)
        item = instant.complete(item.id)
    result = instant.projection(item)
    result["payments"] = [
        payments.projection(p) for p in item.payment_attempts.order_by("created_at")
    ]
    if actor.organization.kind != "clinic":
        for p in result["payments"]:
            p.pop("payment_parameters", None)
    return Response(result)


@api_view(["GET", "POST"])
def bill_payments(request, bill_id):
    actor = request_actor(request)
    bill = finance.get_bill(actor, bill_id)
    require(
        finance.full_bill_access(actor, bill) or not bill.cooperation_id,
        "forbidden",
        "整单付款信息仅签约主体与平台可查看",
        403,
    )
    if request.method == "POST":
        data = validated(PaymentInput, request)
        rate_limit(f"payment:{actor.membership.id}", seconds=60, maximum=10)
        attempt = payments.create_payment(
            actor, bill_id, **data, key=request.headers.get("Idempotency-Key", "")
        )
        return Response(payments.projection(attempt), status=202)

    def projection(item):
        result = payments.projection(item)
        if actor.organization.kind != "clinic":
            result.pop("payment_parameters", None)
        return result

    return paginated(
        request,
        bill.payment_attempts.all(),
        projection,
        states=["creating", "pending", "unknown", "success", "closed"],
    )


class PaymentActionInput(StrictSerializer):
    confirmed = serializers.BooleanField()


@api_view(["POST"])
def payment_action(request, attempt_id, action):
    actor = request_actor(request)
    attempt = payments.get_attempt(actor, attempt_id, operate=True)
    require(action in {"query", "close", "retry"}, "not_found", "支付操作不存在", 404)
    data = validated(PaymentActionInput, request)
    require(data["confirmed"] is True, "confirmation_required", "请确认支付核对操作", 400)
    rate_limit(f"payment-query:{attempt.id}", seconds=60, maximum=6)
    result = (
        payments.retry_preparation(actor, attempt.id)
        if action == "retry"
        else payments.reconcile(attempt.id, close=action == "close")
    )
    return Response(payments.projection(result))


@api_view(["GET"])
def payment_configuration(request):
    request_actor(request)
    # Never return keys, certificate paths or merchant secrets.
    return Response(
        {
            "wechat_enabled": settings.WECHAT_PAY_ENABLED,
            "simulated": settings.ACCEPTANCE_SIMULATED_EXTERNALS,
            "offline_receipt_enabled": True,
        }
    )


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def notification(request):
    require(
        request.content_type == "application/json", "invalid_content_type", "需要JSON支付通知", 415
    )
    length = request.META.get("CONTENT_LENGTH", "0")
    require(
        length.isdigit() and int(length) <= MAX_MESSAGE, "wechat_message_size", "支付报文过大", 413
    )
    raw = request.body
    require(len(raw) <= MAX_MESSAGE, "wechat_message_size", "支付报文过大", 413)
    payments.capture_notification(request.headers, raw)
    return HttpResponse(status=204)
