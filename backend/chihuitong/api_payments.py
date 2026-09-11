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


@api_view(["GET", "POST"])
def bill_payments(request, bill_id):
    actor = request_actor(request)
    bill = finance.get_bill(actor, bill_id)
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
    result = payments.retry_preparation(actor, attempt.id) if action == "retry" else payments.reconcile(attempt.id, close=action == "close")
    return Response(payments.projection(result))


@api_view(["GET"])
def payment_configuration(request):
    request_actor(request)
    # Never return keys, certificate paths or merchant secrets.
    return Response(
        {"wechat_enabled": settings.WECHAT_PAY_ENABLED, "offline_receipt_enabled": True}
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
