from django.db.models import Case, CharField, Value, When
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .api import StrictSerializer, paginated, validated
from .api_catalog import VersionInput
from .errors import require
from .identity import rate_limit, request_actor
from .mini_identity import login, session_profile
from .models import Appointment, Benefit, CustomerMessage, FileAsset, MiniSession
from .services import appointments, customers, discovery, files, payments
from .services.common import audit, customer_audit_context, idempotent
from .services.finance_queries import iso


class LoginInput(StrictSerializer):
    login_code = serializers.CharField(min_length=5, max_length=512)
    phone_code = serializers.CharField(min_length=5, max_length=512)
    name = serializers.CharField(max_length=100, required=False)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def mini_login(request, audience):
    return Response(
        login(
            audience,
            **validated(LoginInput, request),
            remote_address=request.META.get("REMOTE_ADDR", "unknown"),
        )
    )


@api_view(["GET"])
def me(request):
    require(isinstance(request.auth, MiniSession), "invalid_session", "请从对应小程序登录", 403)
    result = session_profile(request.auth)
    if result["audience"] == "customer":
        customer = request.user
        result["profile"] = {
            "number": customer.number,
            "name": customer.name,
            "phone": customer.phone,
            **{key: customer.profile.get(key) for key in ["gender", "age", "occupation"]},
        }
    return Response(result)


def customer_command(request, operation, data, callback):
    def execute():
        with customer_audit_context(request.user):
            result = callback()
            # No field values, QR credentials, or raw request contents in audit metadata.
            audit(
                None,
                request.user,
                "customer." + operation,
                target_id=result.get("id"),
                fields=sorted(data),
            )
            return result

    return idempotent(
        request.user.id,
        "customer." + operation,
        request.headers.get("Idempotency-Key", ""),
        data,
        execute,
    )


class ProfileInput(StrictSerializer):
    name = serializers.CharField(max_length=100, required=False)
    gender = serializers.ChoiceField(
        choices=["male", "female", "unknown"], required=False, allow_null=True
    )
    age = serializers.IntegerField(min_value=0, max_value=150, required=False, allow_null=True)
    occupation = serializers.CharField(
        max_length=100, allow_blank=True, required=False, allow_null=True
    )


@api_view(["POST"])
def profile(request):
    data = validated(ProfileInput, request)

    def update():
        item = customers.update_profile(request.user.id, data)
        return {"id": str(item.id), "name": item.name, "phone": item.phone, "version": item.version}

    return Response(customer_command(request, "profile", data, update))


def benefit_query(customer):
    return (
        Benefit.objects.select_related("card__order", "product")
        .filter(customer=customer)
        .annotate(
            display_status=Case(
                When(card__frozen=True, then=Value("frozen")),
                When(voided__gt=0, then=Value("invalid")),
                When(restoring__gt=0, then=Value("restoring")),
                When(reserved__gt=0, then=Value("reserved")),
                When(expires_at__date__lt=timezone.localdate(), then=Value("expired")),
                When(pending__gt=0, then=Value("pending_claim")),
                When(available__gt=0, then=Value("available")),
                default=Value("used"),
                output_field=CharField(),
            )
        )
    )


def benefit_projection(item):
    order = item.card.order
    return {
        "id": str(item.id),
        "card_id": str(item.card_id),
        "product_id": str(item.product_id),
        "external_name": order.product_snapshot["external_name"],
        "usage_rules": order.product_snapshot["usage_rules"],
        "source_name": order.source_name,
        "total": item.total,
        "pending": item.pending,
        "available": item.available,
        "reserved": item.reserved,
        "used": item.used,
        "restoring": item.restoring,
        "activated_at": iso(item.activated_at),
        "expires_at": iso(item.expires_at),
        "status": item.display_status,
        "can_claim": item.display_status == "pending_claim" and order.status == "issued",
        "can_book": item.display_status == "available",
    }


@api_view(["GET"])
def benefits(request):
    return paginated(
        request,
        benefit_query(request.user),
        benefit_projection,
        status_field="display_status",
        states=[
            "pending_claim",
            "available",
            "reserved",
            "restoring",
            "used",
            "expired",
            "invalid",
            "frozen",
        ],
    )


class ClaimInput(StrictSerializer):
    confirmed = serializers.BooleanField()


class ActivateInput(ClaimInput):
    credential = serializers.CharField(min_length=20, max_length=200, trim_whitespace=False)


@api_view(["POST"])
def claim(request, card_id):
    data = validated(ClaimInput, request)
    require(data["confirmed"] is True, "confirmation_required", "请确认领取权益", 400)

    def apply():
        item = customers.claim(request.user.id, card_id)
        return benefit_projection(benefit_query(request.user).get(pk=item.pk))

    return Response(customer_command(request, "claim", {"card_id": str(card_id), **data}, apply))


@api_view(["POST"])
def activate(request):
    data = validated(ActivateInput, request)
    require(
        data["confirmed"] is True, "confirmation_required", "请确认激活后绑定本人且不可转让", 400
    )

    def apply():
        item = customers.activate(request.user.id, data["credential"])
        return benefit_projection(benefit_query(request.user).get(pk=item.pk))

    return Response(customer_command(request, "activate", data, apply))


def owned_appointments(customer):
    return Appointment.objects.select_related(
        "benefit__card__order", "clinic__organization"
    ).filter(customer=customer)


def appointment_projection(item):
    order, card = item.benefit.card.order, item.benefit.card
    effective = item.redemptions.filter(status="active").first()
    qr = (
        card.credential
        if item.reserved
        and not card.frozen
        and item.status in {"success", "completed"}
        and not effective
        else None
    )
    return {
        "id": str(item.id),
        "version": item.version,
        "status": item.status,
        "completion_source": item.completion_source,
        "requested_at": iso(item.requested_at),
        "scheduled_at": iso(item.scheduled_at),
        "pending_deadline": iso(item.pending_deadline),
        "clinic_id": str(item.clinic_id),
        "clinic_name": item.clinic.organization.name,
        "frontdesk_phone": item.clinic.profile.get("frontdesk_phone"),
        "benefit_id": str(item.benefit_id),
        "external_name": order.product_snapshot["external_name"],
        "usage_rules": order.product_snapshot["usage_rules"],
        "source_name": order.source_name,
        "redemption_qr": qr,
        "restoration_pending": item.restoration_pending,
        "conflict": item.conflict,
        "clinic_settled": bool(effective and effective.settled_at),
        "cancellation_reason": item.cancellation_reason,
        "pending_reschedule": item.reschedules.filter(status="pending")
        .values("id", "proposed_at", "expires_at")
        .first(),
    }


class BookingInput(StrictSerializer):
    benefit_id = serializers.UUIDField()
    clinic_id = serializers.UUIDField()
    requested_at = serializers.DateTimeField()


@api_view(["GET", "POST"])
def appointment_list(request):
    if request.method == "POST":
        data = validated(BookingInput, request)
        return Response(
            customer_command(
                request,
                "book",
                data,
                lambda: appointment_projection(appointments.book(request.user.id, **data)),
            ),
            status=201,
        )
    return paginated(
        request,
        owned_appointments(request.user),
        appointment_projection,
        states=["pending", "success", "completed", "cancelled"],
    )


@api_view(["GET"])
def appointment_detail(request, appointment_id):
    item = owned_appointments(request.user).filter(pk=appointment_id).first()
    require(item, "not_found", "预约不存在", 404)
    return Response(appointment_projection(item))


class CancelInput(VersionInput):
    reason = serializers.CharField(max_length=500)


class RescheduleInput(VersionInput):
    proposed_at = serializers.DateTimeField()


class FeedbackInput(VersionInput):
    arrived = serializers.BooleanField()
    confirmed = serializers.BooleanField()


class RestoreInput(VersionInput):
    confirmed = serializers.BooleanField()


@api_view(["POST"])
def appointment_action(request, appointment_id, action):
    item = owned_appointments(request.user).filter(pk=appointment_id).first()
    require(item, "not_found", "预约不存在", 404)
    schemas = {
        "cancel": CancelInput,
        "reschedule": RescheduleInput,
        "feedback": FeedbackInput,
        "restore": RestoreInput,
    }
    require(action in schemas, "not_found", "操作不存在", 404)
    data = validated(schemas[action], request)

    def apply():
        if action == "cancel":
            appointments.cancel(appointment_id, customer_id=request.user.id, **data)
        elif action == "reschedule":
            appointments.reschedule(appointment_id, customer_id=request.user.id, **data)
        elif action == "feedback":
            appointments.customer_feedback(request.user.id, appointment_id, **data)
        else:
            appointments.restore_reversal(request.user.id, appointment_id, **data)
        return appointment_projection(owned_appointments(request.user).get(pk=appointment_id))

    return Response(
        customer_command(
            request, "appointment." + action, {"appointment_id": str(appointment_id), **data}, apply
        )
    )


def message_projection(item):
    return {
        "id": str(item.id),
        "appointment_id": str(item.appointment_id),
        "kind": item.kind,
        "status": item.status,
        "read_at": iso(item.read_at),
        "resolved_at": iso(item.resolved_at),
        "title": "补核销已撤销，请确认是否申请恢复权益"
        if item.kind == "reversal_restoration"
        else "请确认是否到诊；确实未到诊可申请恢复权益",
        "action": "restore" if item.kind == "reversal_restoration" else "feedback",
        "appointment": appointment_projection(item.appointment),
    }


@api_view(["GET"])
def messages(request):
    return paginated(
        request,
        CustomerMessage.objects.filter(customer=request.user).select_related(
            "appointment__benefit__card__order", "appointment__clinic__organization"
        ),
        message_projection,
        states=["pending", "resolved"],
    )


@api_view(["POST"])
def message_read(request, message_id):
    item = CustomerMessage.objects.filter(pk=message_id, customer=request.user).first()
    require(item, "not_found", "消息不存在", 404)
    if not item.read_at:
        item.read_at = timezone.now()
        item.save(update_fields=["read_at"])
    return Response({"read": True, "business_status": item.status})


@api_view(["POST"])
def clinic_payment(request, bill_id):
    actor = request_actor(request)
    actor.require_admin()
    rate_limit(f"payment:{actor.membership.id}", seconds=60, maximum=10)
    data = validated(VersionInput, request)
    require(
        isinstance(request.auth, MiniSession) and request.auth.audience == "clinic",
        "invalid_session",
        "请通过门诊小程序付款",
        403,
    )
    identity = request.auth.identity
    attempt = payments.create_payment(
        actor,
        bill_id,
        version=data["version"],
        method="jsapi",
        key=request.headers.get("Idempotency-Key", ""),
        verified_openid=identity.openid,
        verified_appid=identity.appid,
    )
    return Response(payments.projection(attempt))


class DiscoveryInput(StrictSerializer):
    benefit_id = serializers.UUIDField()
    longitude = serializers.DecimalField(
        max_digits=10, decimal_places=6, min_value=-180, max_value=180, required=False
    )
    latitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, min_value=-90, max_value=90, required=False
    )
    query = serializers.CharField(max_length=100, required=False, allow_blank=True)
    page = serializers.IntegerField(min_value=1, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=100, default=20)


@api_view(["GET"])
def clinic_search(request):
    form = DiscoveryInput(data=request.query_params.dict())
    form.is_valid(raise_exception=True)
    data = dict(form.validated_data)
    require(
        ("longitude" in data) == ("latitude" in data),
        "coordinates_required",
        "请同时提供经纬度",
        400,
    )
    page, size = data.pop("page"), data.pop("page_size")
    qs = discovery.listing(request.user, **data)
    return Response(
        {
            "results": [discovery.projection(row) for row in qs[(page - 1) * size : page * size]],
            "total": qs.count(),
            "page": page,
            "page_size": size,
        }
    )


def customer_clinic(request, clinic_id):
    raw = request.query_params.get("benefit_id")
    benefit_id = serializers.UUIDField().run_validation(raw) if raw else None
    return discovery.detail(request.user, clinic_id, benefit_id=benefit_id)


@api_view(["GET"])
def clinic_detail(request, clinic_id):
    return Response(discovery.projection(customer_clinic(request, clinic_id)))


@api_view(["GET"])
def clinic_cover(request, clinic_id):
    clinic = customer_clinic(request, clinic_id)
    asset = FileAsset.objects.filter(
        pk=clinic.profile.get("cover_id"),
        status="ready",
        purpose="cover",
        content_type="image/jpeg",
    ).first()
    require(asset, "not_found", "门诊尚未设置展示图片", 404)
    response = HttpResponse(files.file_bytes(asset), content_type="image/jpeg")
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
