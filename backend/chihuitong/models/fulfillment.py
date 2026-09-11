from django.db import models
from django.db.models import Q

from chihuitong.crypto import EncryptedTextField

from .catalog import Clinic
from .core import Entity, Membership, Organization
from .sales import Benefit, Customer


class Appointment(Entity):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT)
    benefit = models.ForeignKey(Benefit, on_delete=models.PROTECT, related_name="appointments")
    clinic = models.ForeignKey(Clinic, on_delete=models.PROTECT, related_name="appointments")
    booked_channel = models.ForeignKey(Organization, on_delete=models.PROTECT)
    requested_at = models.DateTimeField()
    scheduled_at = models.DateTimeField(null=True)
    pending_deadline = models.DateTimeField()
    units = models.PositiveIntegerField()
    status = models.CharField(max_length=16, default="pending")
    completion_source = models.CharField(max_length=16, blank=True)
    completed_at = models.DateTimeField(null=True)
    cancellation_reason = EncryptedTextField(default="")
    reserved = models.BooleanField(default=True)
    patient_arrived_at = models.DateTimeField(null=True)
    clinic_absent_at = models.DateTimeField(null=True)
    conflict = models.BooleanField(default=False)
    restoration_pending = models.BooleanField(default=False)
    schedule_revision = models.PositiveIntegerField(default=1)
    restoration_round = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(status__in=["pending", "success", "completed", "cancelled"]), name="appointment_states"),
            models.CheckConstraint(condition=Q(units__gt=0), name="appointment_units_positive"),
        ]
        indexes = [models.Index(fields=["clinic", "status", "scheduled_at"])]


class Reschedule(Entity):
    appointment = models.ForeignKey(Appointment, on_delete=models.PROTECT, related_name="reschedules")
    previous_at = models.DateTimeField()
    proposed_at = models.DateTimeField()
    initiated_by = models.CharField(max_length=16)
    actor = models.ForeignKey(Membership, null=True, on_delete=models.PROTECT)
    status = models.CharField(max_length=16, default="pending")
    agreed = models.BooleanField(default=False)
    expires_at = models.DateTimeField()
    reviewed_by = models.ForeignKey(Membership, null=True, on_delete=models.PROTECT, related_name="reschedule_reviews")
    reviewed_at = models.DateTimeField(null=True)
    reason = EncryptedTextField(default="")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["appointment"], condition=Q(status="pending"), name="one_pending_reschedule")]


class Redemption(Entity):
    appointment = models.ForeignKey(Appointment, on_delete=models.PROTECT, related_name="redemptions")
    actor = models.ForeignKey(Membership, on_delete=models.PROTECT)
    resource = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="source_redemptions")
    channel = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="channel_redemptions")
    status = models.CharField(max_length=16, default="active")
    fee_cents = models.PositiveBigIntegerField()
    resource_cents = models.PositiveBigIntegerField()
    channel_cents = models.PositiveBigIntegerField()
    platform_cents = models.PositiveBigIntegerField()
    units = models.PositiveIntegerField()
    snapshot = models.JSONField()
    previous_completion_source = models.CharField(max_length=16, blank=True)
    settled_at = models.DateTimeField(null=True)
    reversed_at = models.DateTimeField(null=True)
    reversed_by = models.ForeignKey(Membership, null=True, on_delete=models.PROTECT, related_name="reversal_actions")
    reversal_reason = EncryptedTextField(default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["appointment"], condition=Q(status="active"), name="one_active_redemption"),
            models.CheckConstraint(condition=Q(fee_cents=models.F("resource_cents") + models.F("channel_cents") + models.F("platform_cents")), name="redemption_money_conservation"),
        ]


class FulfillmentTask(Entity):
    appointment = models.ForeignKey(Appointment, on_delete=models.PROTECT, related_name="fulfillment_tasks")
    kind = models.CharField(max_length=24)
    round = models.PositiveIntegerField()
    status = models.CharField(max_length=16, default="pending")
    closed_at = models.DateTimeField(null=True)
    close_reason = models.CharField(max_length=80, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["appointment", "kind", "round"], name="fulfillment_task_round")]


class CustomerMessage(Entity):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT)
    appointment = models.ForeignKey(Appointment, on_delete=models.PROTECT)
    kind = models.CharField(max_length=40)
    round = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=16, default="pending")
    read_at = models.DateTimeField(null=True)
    resolved_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["appointment", "kind", "round"], name="customer_message_round")]
