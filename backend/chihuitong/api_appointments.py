import hashlib
import json

from django.db.models import Exists, OuterRef
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .api import StrictSerializer, paginated, validated
from .api_catalog import VersionInput
from .api_sales import ReviewInput, command
from .crypto import digest
from .errors import require
from .exports import excel_response
from .identity import request_actor
from .models import FulfillmentTask, Redemption, Reschedule
from .services import appointments
from .services.common import RESOURCE_KINDS, audit
from .services.finance_queries import iso, transaction_projection


def appointment_projection(actor, item):
    phone = item.customer.phone
    if not actor.platform and actor.organization.kind not in RESOURCE_KINDS | {"clinic"}:
        phone = phone[:3] + "****" + phone[-4:]
    active = item.redemptions.filter(status="active").first()
    order = item.benefit.card.order
    result = {
        "id": str(item.id),
        "version": item.version,
        "status": item.status,
        "customer_number": item.customer.number,
        "customer_name": item.customer.name,
        "phone": phone,
        "clinic_id": str(item.clinic_id),
        "clinic_name": item.clinic.organization.name,
        "benefit_id": str(item.benefit_id),
        "product_id": str(item.benefit.product_id),
        "internal_name": order.product_snapshot.get(
            "internal_name", item.benefit.product.internal_name
        ),
        "external_name": order.product_snapshot["external_name"],
        "source_name": order.source_name,
        "units": item.units,
        "requested_at": iso(item.requested_at),
        "scheduled_at": iso(item.scheduled_at),
        "pending_deadline": iso(item.pending_deadline),
        "completed_at": iso(item.completed_at),
        "completion_source": item.completion_source,
        "cancellation_reason": item.cancellation_reason,
        "reserved": item.reserved,
        "restoration_pending": item.restoration_pending,
        "patient_arrived_at": iso(item.patient_arrived_at),
        "clinic_absent_at": iso(item.clinic_absent_at),
        "conflict": item.conflict,
        "clinic_settled": bool(active and active.settled_at),
        "settlement_status": "settled"
        if active and active.settled_at
        else "unsettled"
        if active
        else "not_charged",
        "redemption_id": str(active.id) if active else None,
        "settled_at": iso(active.settled_at) if active else None,
    }
    return result


def scoped(request, actor):
    query = appointments.visible_appointments(actor).select_related(
        "clinic__organization", "benefit__product"
    )
    for field in ["clinic_id", "customer_id", "benefit__product_id"]:
        key = "product_id" if field == "benefit__product_id" else field
        if request.query_params.get(key):
            query = query.filter(
                **{field: serializers.UUIDField().run_validation(request.query_params[key])}
            )
    if request.query_params.get("settled"):
        value = serializers.BooleanField().run_validation(request.query_params["settled"])
        query = query.annotate(
            is_settled=Exists(
                Redemption.objects.filter(
                    appointment_id=OuterRef("pk"), status="active", settled_at__isnull=False
                )
            )
        ).filter(is_settled=value)
    for key, lookup in [
        ("date_from", "scheduled_at__date__gte"),
        ("date_to", "scheduled_at__date__lte"),
    ]:
        if request.query_params.get(key):
            query = query.filter(
                **{lookup: serializers.DateField().run_validation(request.query_params[key])}
            )
    return query


def get_appointment(actor, appointment_id):
    item = appointments.visible_appointments(actor).filter(pk=appointment_id).first()
    require(item, "not_found", "预约不存在", 404)
    return item


@api_view(["GET"])
def appointment_list(request):
    actor = request_actor(request)
    return paginated(
        request,
        scoped(request, actor),
        lambda item: appointment_projection(actor, item),
        states=["pending", "success", "completed", "cancelled"],
    )


@api_view(["GET"])
def appointment_detail(request, appointment_id):
    actor = request_actor(request)
    item = get_appointment(actor, appointment_id)
    return Response(
        {
            **appointment_projection(actor, item),
            "reschedules": [
                reschedule_projection(change) for change in item.reschedules.order_by("created_at")
            ],
            "redemptions": [
                transaction_projection(actor, row)
                for row in item.redemptions.order_by("created_at")
            ],
        }
    )


class ConfirmInput(VersionInput):
    scheduled_at = serializers.DateTimeField()


class CancelInput(VersionInput):
    reason = serializers.CharField(max_length=500)


class RescheduleInput(VersionInput):
    proposed_at = serializers.DateTimeField()
    agreed = serializers.BooleanField()


class AttendanceInput(VersionInput):
    confirmed = serializers.BooleanField()


def reschedule_projection(item):
    return {
        "id": str(item.id),
        "appointment_id": str(item.appointment_id),
        "version": item.version,
        "previous_at": iso(item.previous_at),
        "proposed_at": iso(item.proposed_at),
        "status": item.status,
        "initiated_by": item.initiated_by,
        "agreed": item.agreed,
        "expires_at": iso(item.expires_at),
        "reviewed_at": iso(item.reviewed_at),
        "reason": item.reason,
    }


@api_view(["POST"])
def appointment_action(request, appointment_id, action):
    actor = request_actor(request)
    item = get_appointment(actor, appointment_id)
    appointments.clinic_actor(actor, item)
    operations = {
        "confirm": (
            ConfirmInput,
            lambda data: appointment_projection(
                actor, appointments.confirm(actor, appointment_id, **data)
            ),
        ),
        "cancel": (
            CancelInput,
            lambda data: appointment_projection(
                actor, appointments.cancel(appointment_id, actor=actor, **data)
            ),
        ),
        "reschedule": (
            RescheduleInput,
            lambda data: reschedule_projection(
                appointments.reschedule(appointment_id, actor=actor, **data)
            ),
        ),
        "report-absent": (
            AttendanceInput,
            lambda data: appointment_projection(
                actor, appointments.report_absent(actor, appointment_id, **data)
            ),
        ),
    }
    require(action in operations, "not_found", "操作不存在", 404)
    schema, operation = operations[action]
    data = validated(schema, request)
    return Response(
        command(
            request,
            actor,
            f"appointment.{action}",
            {"appointment_id": str(appointment_id), **data},
            lambda: operation(data),
        )
    )


@api_view(["GET"])
def reschedules(request):
    actor = request_actor(request)
    return paginated(
        request,
        Reschedule.objects.filter(appointment__in=appointments.visible_appointments(actor)),
        reschedule_projection,
        states=["pending", "approved", "rejected", "expired", "cancelled"],
    )


@api_view(["POST"])
def reschedule_review(request, change_id):
    actor = request_actor(request)
    change = Reschedule.objects.filter(
        pk=change_id, appointment__in=appointments.visible_appointments(actor)
    ).first()
    require(change, "not_found", "改期申请不存在", 404)
    appointments.clinic_actor(actor, change.appointment)
    data = validated(ReviewInput, request)
    return Response(
        command(
            request,
            actor,
            "appointment.reschedule_review",
            {"change_id": str(change_id), **data},
            lambda: reschedule_projection(appointments.review_reschedule(actor, change_id, **data)),
        )
    )


class ScanInput(StrictSerializer):
    credential = serializers.CharField(min_length=20, max_length=200)


class QuoteInput(ScanInput):
    appointment_id = serializers.UUIDField()


class RedeemInput(QuoteInput):
    version = serializers.IntegerField(min_value=1)
    confirmed = serializers.BooleanField()
    quote = serializers.CharField(max_length=3000)


@api_view(["POST"])
def scan(request):
    actor = request_actor(request)
    require(actor.organization.kind == "clinic", "forbidden", "仅门诊工作人员可以扫码核销", 403)
    credential = validated(ScanInput, request)["credential"]
    query = appointments.visible_appointments(actor).filter(
        benefit__card__credential_digest=digest(credential, purpose="card"),
        reserved=True,
        status__in=["success", "completed"],
        restoration_pending=False,
    )
    require(query.exists(), "no_matching_appointment", "此卡没有本门诊可处理的预约", 404)
    return Response(
        {
            "results": [
                appointment_projection(actor, item) for item in query.order_by("scheduled_at")
            ]
        }
    )


@api_view(["POST"])
def redemption_quote(request):
    actor = request_actor(request)
    data = validated(QuoteInput, request)
    get_appointment(actor, data["appointment_id"])
    return Response(appointments.redemption_quote(actor, **data))


@api_view(["POST"])
def redeem(request):
    actor = request_actor(request)
    data = validated(RedeemInput, request)
    item = get_appointment(actor, data["appointment_id"])
    appointments.clinic_actor(actor, item)
    return Response(
        command(
            request,
            actor,
            "appointment.redeem",
            data,
            lambda: transaction_projection(actor, appointments.redeem(actor, **data)),
        )
    )


@api_view(["POST"])
def reverse_redemption(request, redemption_id):
    actor = request_actor(request)
    ref = Redemption.objects.filter(
        pk=redemption_id, appointment__in=appointments.visible_appointments(actor)
    ).first()
    require(ref, "not_found", "核销记录不存在", 404)
    appointments.clinic_actor(actor, ref.appointment)
    data = validated(CancelInput, request)
    return Response(
        command(
            request,
            actor,
            "appointment.reverse",
            {"redemption_id": str(redemption_id), **data},
            lambda: transaction_projection(
                actor, appointments.reverse_redemption(actor, redemption_id, **data)
            ),
        )
    )


@api_view(["GET"])
def fulfillment_tasks(request):
    actor = request_actor(request)
    qs = FulfillmentTask.objects.filter(appointment__in=appointments.visible_appointments(actor))
    return paginated(
        request,
        qs,
        lambda item: {
            "id": str(item.id),
            "kind": item.kind,
            "status": item.status,
            "created_at": iso(item.created_at),
            "closed_at": iso(item.closed_at),
            "close_reason": item.close_reason,
            "appointment": appointment_projection(actor, item.appointment),
        },
        states=["pending", "conflict", "closed"],
    )


@api_view(["GET"])
def reminder_snapshot(request):
    actor = request_actor(request)
    require(actor.organization.kind == "clinic", "forbidden", "此提醒仅用于门诊工作区", 403)
    query = appointments.visible_appointments(actor).filter(
        status="pending", pending_deadline__gt=timezone.now()
    )
    rows = [
        {
            "id": str(item.id),
            "version": item.version,
            "requested_at": iso(item.requested_at),
            "created_at": iso(item.created_at),
        }
        for item in query.order_by("created_at", "id")
    ]
    revision = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
    return Response(
        {
            "revision": revision,
            "count": len(rows),
            "appointments": rows,
            "poll_after_seconds": 5,
            "server_time": iso(timezone.now()),
        }
    )


@api_view(["GET"])
def appointment_export(request):
    actor = request_actor(request)
    qs = scoped(request, actor)
    status = request.query_params.get("status", "all")
    require(
        status in {"all", "pending", "success", "completed", "cancelled"},
        "invalid_status",
        "预约状态不合法",
        400,
    )
    if status != "all":
        qs = qs.filter(status=status)
    audit(actor, actor.organization, "appointment.exported", count=qs.count(), status=status)
    keys = [
        "id",
        "customer_number",
        "customer_name",
        "phone",
        "internal_name",
        "source_name",
        "clinic_name",
        "status",
        "scheduled_at",
        "completion_source",
        "settlement_status",
    ]

    def rows():
        for item in qs.order_by("created_at", "id").iterator():
            data = appointment_projection(actor, item)
            yield [data[key] for key in keys]

    return excel_response(
        [
            "预约编号",
            "客户编号",
            "客户姓名",
            "手机号",
            "推广产品",
            "权益来源",
            "门诊",
            "预约状态",
            "预约时间",
            "完成方式",
            "门诊结算状态",
        ],
        rows(),
        filename="appointments.xlsx",
    )
