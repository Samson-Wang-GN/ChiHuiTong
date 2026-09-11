from django.db import models

from chihuitong.crypto import EncryptedJSONField, EncryptedTextField

from .core import Entity, Membership


class Notification(Entity):
    recipient = models.ForeignKey(Membership, on_delete=models.PROTECT)
    dedup_key = models.CharField(max_length=200)
    kind = models.CharField(max_length=80)
    object_type = models.CharField(max_length=80)
    object_id = models.UUIDField()
    title = models.CharField(max_length=200)
    status = models.CharField(max_length=16, default="unread")
    read_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["recipient", "dedup_key"], name="notification_recipient_once"
            )
        ]


class SmsTemplate(Entity):
    code = models.CharField(max_length=80, unique=True)
    name = models.CharField(max_length=100)
    content = models.CharField(max_length=1000)
    parameter_names = models.JSONField(default=list)
    provider_template_id = models.CharField(max_length=100, blank=True)
    sign_name = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=16, default="disabled")


class SmsDelivery(Entity):
    dedup_key = models.CharField(max_length=200, unique=True)
    template = models.ForeignKey(SmsTemplate, on_delete=models.PROTECT)
    template_version = models.PositiveIntegerField()
    phone = EncryptedTextField()
    parameters = EncryptedJSONField(default=dict)
    status = models.CharField(max_length=16, default="pending")
    attempts = models.PositiveIntegerField(default=0)
    provider_reference = EncryptedTextField(default="")
    last_error_code = models.CharField(max_length=80, blank=True)
    accepted_at = models.DateTimeField(null=True)
    # Accepted means provider accepted; never label this as handset delivery confirmed.


class SmsAttempt(Entity):
    delivery = models.ForeignKey(SmsDelivery, on_delete=models.PROTECT, related_name="history")
    number = models.PositiveIntegerField()
    template_version = models.PositiveIntegerField()
    template_snapshot = models.JSONField(default=dict)
    status = models.CharField(max_length=16, default="sending")
    error_code = models.CharField(max_length=80, blank=True)
    provider_reference = EncryptedTextField(default="")
    finished_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["delivery", "number"], name="sms_attempt_number")
        ]
