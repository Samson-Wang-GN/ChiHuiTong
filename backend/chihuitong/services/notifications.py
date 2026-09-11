import re

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.module_loading import import_string

from chihuitong.errors import BusinessError, require
from chihuitong.models import Appointment, Membership, Notification, SmsDelivery, SmsTemplate

from .common import advance, advisory_lock, audit, check_version

TEMPLATES = {
    "login": (
        "登录验证码",
        "您的验证码为{code}，{minutes}分钟内有效，请勿泄露。",
        ["code", "minutes"],
    ),
    "appointment.new": (
        "新预约",
        "您有新的预约{appointment_number}，请登录齿慧通确认。",
        ["appointment_number"],
    ),
    "appointment.cancelled": (
        "预约取消",
        "预约{appointment_number}已取消，请登录齿慧通查看。",
        ["appointment_number"],
    ),
    "appointment.reschedule": (
        "客户改期申请",
        "预约{appointment_number}有改期申请，请及时处理。",
        ["appointment_number"],
    ),
    "appointment.supplement": (
        "客户到诊反馈",
        "预约{appointment_number}有到诊反馈，请核对并补充核销。",
        ["appointment_number"],
    ),
    "appointment.restored": (
        "客户恢复权益",
        "预约{appointment_number}已由客户申请恢复权益，请查看。",
        ["appointment_number"],
    ),
    "appointment.overdue": (
        "过期预约待办",
        "预约{appointment_number}已过期24小时，请核对履约结果。",
        ["appointment_number"],
    ),
    "bill.reminder": (
        "门诊付款提醒",
        "账单{bill_number}待付{amount}元，请于{due_date}前处理。",
        ["bill_number", "amount", "due_date"],
    ),
    "bill.overdue": (
        "门诊付款逾期",
        "账单{bill_number}待付{amount}元，已超过{due_date}，请核对付款。",
        ["bill_number", "amount", "due_date"],
    ),
}


@transaction.atomic
def seed_templates():
    for code, (name, content, parameters) in TEMPLATES.items():
        SmsTemplate.objects.get_or_create(
            code=code, defaults={"name": name, "content": content, "parameter_names": parameters}
        )


@transaction.atomic
def configure_template(
    actor,
    code,
    *,
    content,
    parameter_names,
    provider_template_id,
    sign_name,
    status,
    version,
    reason,
):
    actor.require_platform()
    require(code in TEMPLATES, "unknown_template", "仅可配置预置通知模板", 400)
    item = SmsTemplate.objects.select_for_update().filter(code=code).first()
    require(item, "not_found", "模板尚未初始化", 404)
    check_version(item, version)
    require(
        isinstance(content, str)
        and 1 <= len(content) <= 1000
        and isinstance(parameter_names, list)
        and all(isinstance(value, str) for value in parameter_names),
        "invalid_template",
        "模板内容或变量不合法",
        400,
    )
    allowed = set(TEMPLATES[code][2])
    fields = set(re.findall(r"\{([a-z_]+)\}", content))
    require(
        set(parameter_names) == fields
        and fields <= allowed
        and len(parameter_names) == len(fields)
        and (code != "login" or "code" in fields),
        "invalid_parameters",
        "请核对预置变量及服务商变量顺序",
        400,
    )
    residue = re.sub(r"\{[a-z_]+\}", "", content)
    require(
        "{" not in residue and "}" not in residue, "invalid_template", "模板变量格式不合法", 400
    )
    require(
        status in {"active", "disabled"} and isinstance(reason, str) and reason.strip(),
        "reason_required",
        "请填写模板状态及修改原因",
        400,
    )
    require(
        status != "active"
        or (re.fullmatch(r"[0-9]{1,100}", provider_template_id or "") and sign_name.strip()),
        "provider_template_required",
        "启用前请填写已报备模板编号和签名",
        400,
    )
    item.content, item.parameter_names, item.provider_template_id, item.sign_name, item.status = (
        content,
        parameter_names,
        provider_template_id,
        sign_name,
        status,
    )
    advance(item, "content", "parameter_names", "provider_template_id", "sign_name", "status")
    audit(actor, item, "sms_template.configured", reason=reason, version=item.version)
    return item


def notify_members(members, *, kind, obj, title, key):
    for member in members.filter(active=True, account__active=True, organization__status="active"):
        Notification.objects.get_or_create(
            recipient=member,
            dedup_key=key,
            defaults={
                "kind": kind,
                "object_type": obj._meta.model_name,
                "object_id": obj.id,
                "title": title,
            },
        )


def clinic_message(appointment, kind):
    members = Membership.objects.filter(organization_id=appointment.clinic.organization_id)
    notify_members(
        members,
        kind=kind,
        obj=appointment,
        title=TEMPLATES[kind][0],
        key=f"{kind}:{appointment.id}:{appointment.version}",
    )


def send_business(job):
    payload = job.payload
    template = SmsTemplate.objects.filter(code=payload.get("template"), status="active").first()
    require(template, "sms_template_unavailable", "业务短信模板尚未启用", 503)
    parameters = payload.get("parameters", {})
    if payload.get("appointment_id"):
        appointment = Appointment.objects.filter(pk=payload["appointment_id"]).first()
        require(appointment, "notification_target_missing", "预约通知目标不存在", 409)
        # A late new-booking message must not imply an already-processed appointment is pending.
        if payload["template"] == "appointment.new" and appointment.status != "pending":
            return
        parameters = {"appointment_number": appointment.id.hex[-8:].upper()}
    require(
        set(template.parameter_names) <= set(parameters),
        "sms_parameter_missing",
        "短信变量缺失",
        409,
    )
    with transaction.atomic():
        advisory_lock("sms_delivery", job.dedup_key)
        delivery, _ = SmsDelivery.objects.get_or_create(
            dedup_key=job.dedup_key,
            defaults={
                "template": template,
                "template_version": template.version,
                "phone": payload["phone"],
                "parameters": parameters,
            },
        )
        if delivery.status == "accepted":
            return
        delivery.attempts += 1
        delivery.status = "sending"
        advance(delivery, "attempts", "status")
    backend = settings.SMS_BACKEND
    require(
        settings.ENVIRONMENT != "production"
        or backend
        in {
            "chihuitong.integrations.tencent_sms.TencentSMS",
            "chihuitong.integrations.sms.DisabledSMS",
        },
        "unsafe_sms_backend",
        "生产环境禁止测试短信服务",
        503,
    )
    try:
        gateway = import_string(backend)()
        reference = gateway.send_template(
            delivery.phone, template, parameters, context=str(delivery.id)
        )
    except BusinessError as exc:
        SmsDelivery.objects.filter(pk=delivery.id).update(
            status="unknown" if exc.status >= 500 else "failed", last_error_code=exc.code
        )
        raise
    delivery.status, delivery.provider_reference, delivery.accepted_at = (
        "accepted",
        reference,
        timezone.now(),
    )
    advance(delivery, "status", "provider_reference", "accepted_at")


@transaction.atomic
def mark_read(actor, notification_id):
    item = (
        Notification.objects.select_for_update()
        .filter(pk=notification_id, recipient=actor.membership)
        .first()
    )
    require(item, "not_found", "通知不存在", 404)
    if item.status == "unread":
        item.status, item.read_at = "read", timezone.now()
        advance(item, "status", "read_at")
    return item
