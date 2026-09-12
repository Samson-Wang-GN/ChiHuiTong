from django.db import transaction
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .api import StrictSerializer, paginated, validated
from .api_catalog import VersionInput
from .api_sales import command
from .crypto import masked_phone
from .errors import require
from .identity import request_actor
from .models import BusinessCalendar, Notification, Outbox, SmsDelivery, SmsTemplate
from .services import notifications, scheduler
from .services.common import audit
from .services.finance_queries import iso


def notification_projection(item):
    return {
        "id": str(item.id),
        "kind": item.kind,
        "title": item.title,
        "object_type": item.object_type,
        "object_id": str(item.object_id),
        "status": item.status,
        "read_at": iso(item.read_at),
        "created_at": iso(item.created_at),
        "version": item.version,
    }


@api_view(["GET"])
def notification_list(request):
    actor = request_actor(request)
    return paginated(
        request,
        Notification.objects.filter(recipient=actor.membership),
        notification_projection,
        states=["unread", "read"],
    )


@api_view(["POST"])
def notification_read(request, notification_id):
    return Response(
        notification_projection(notifications.mark_read(request_actor(request), notification_id))
    )


def template_projection(item):
    return {
        "id": str(item.id),
        "code": item.code,
        "name": item.name,
        "content": item.content,
        "parameter_names": item.parameter_names,
        "provider_template_id": item.provider_template_id,
        "sign_name": item.sign_name,
        "status": item.status,
        "version": item.version,
    }


@api_view(["GET"])
def templates(request):
    actor = request_actor(request)
    actor.require_platform()
    return paginated(
        request, SmsTemplate.objects.all(), template_projection, states=["active", "disabled"]
    )


class TemplateInput(VersionInput):
    content = serializers.CharField(max_length=1000)
    parameter_names = serializers.ListField(
        child=serializers.CharField(max_length=50), max_length=10
    )
    provider_template_id = serializers.CharField(max_length=100, allow_blank=True)
    sign_name = serializers.CharField(max_length=100, allow_blank=True)
    status = serializers.ChoiceField(choices=["active", "disabled"])
    reason = serializers.CharField(max_length=500)


@api_view(["POST"])
def configure_template(request, code):
    actor = request_actor(request)
    actor.require_platform()
    data = validated(TemplateInput, request)
    return Response(
        command(
            request,
            actor,
            "sms.configure",
            {"code": code, **data},
            lambda: template_projection(notifications.configure_template(actor, code, **data)),
        )
    )


@api_view(["GET"])
def sms_deliveries(request):
    actor = request_actor(request)
    actor.require_platform()
    return paginated(
        request,
        SmsDelivery.objects.select_related("template"),
        lambda item: {
            "id": str(item.id),
            "template_code": item.template.code,
            "template_version": item.template_version,
            "phone": masked_phone(item.phone),
            "status": item.status,
            "attempts": item.attempts,
            "last_error_code": item.last_error_code,
            "accepted_at": iso(item.accepted_at),
            "simulated": item.provider_reference.startswith("SIMULATED-"),
            "created_at": iso(item.created_at),
        },
        states=["pending", "sending", "unknown", "failed", "accepted"],
    )


def job_projection(item):
    return {
        "id": str(item.id),
        "kind": item.kind,
        "status": item.status,
        "attempts": item.attempts,
        "available_at": iso(item.available_at),
        "locked_until": iso(item.locked_until),
        "last_error_code": item.last_error_code,
        "version": item.version,
    }


@api_view(["GET"])
def sms_history(request, delivery_id):
    actor = request_actor(request)
    actor.require_platform()
    delivery = SmsDelivery.objects.filter(pk=delivery_id).first()
    require(delivery, "not_found", "短信发送记录不存在", 404)
    return paginated(
        request,
        delivery.history.all(),
        lambda item: {
            "id": str(item.id),
            "attempt": item.number,
            "template_version": item.template_version,
            "template": item.template_snapshot,
            "status": item.status,
            "error_code": item.error_code,
            "created_at": iso(item.created_at),
            "finished_at": iso(item.finished_at),
            "simulated": item.provider_reference.startswith("SIMULATED-"),
        },
        states=["sending", "unknown", "failed", "accepted"],
    )


@api_view(["GET"])
def jobs(request):
    actor = request_actor(request)
    actor.require_platform()
    return paginated(
        request,
        Outbox.objects.all(),
        job_projection,
        states=["pending", "running", "failed", "done"],
    )


class RetryInput(StrictSerializer):
    reason = serializers.CharField(max_length=500)


@api_view(["POST"])
def retry_job(request, job_id):
    actor = request_actor(request)
    actor.require_platform()
    data = validated(RetryInput, request)
    return Response(
        command(
            request,
            actor,
            "job.retry",
            {"job_id": str(job_id), **data},
            lambda: job_projection(scheduler.retry_job(actor, job_id, **data)),
        )
    )


class CalendarInput(StrictSerializer):
    working = serializers.BooleanField()
    note = serializers.CharField(max_length=200)


@api_view(["GET", "POST"])
def calendar_day(request, date):
    actor = request_actor(request)
    actor.require_platform()
    day = serializers.DateField().run_validation(date)
    if request.method == "POST":
        data = validated(CalendarInput, request)
        with transaction.atomic():
            item, _ = BusinessCalendar.objects.update_or_create(date=day, defaults=data)
            audit(
                actor,
                actor.organization,
                "calendar.updated",
                date=day.isoformat(),
                working=item.working,
            )
    else:
        item = BusinessCalendar.objects.filter(date=day).first()
    return Response(
        {
            "date": day.isoformat(),
            "working": item.working if item else day.weekday() < 5,
            "override": bool(item),
            "note": item.note if item else "未配置调休，默认周一至周五",
        }
    )


@api_view(["GET"])
def calendar_list(request):
    actor = request_actor(request)
    actor.require_platform()
    year = serializers.IntegerField(min_value=2020, max_value=2100).run_validation(
        request.query_params.get("year")
    )
    return Response(
        {
            "year": year,
            "results": [
                {"date": item.date.isoformat(), "working": item.working, "note": item.note}
                for item in BusinessCalendar.objects.filter(date__year=year).order_by("date")
            ],
        }
    )
