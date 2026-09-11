from django.db import models
from django.db.models import Q

from chihuitong.crypto import EncryptedJSONField, EncryptedTextField

from .catalog import Clinic
from .core import Entity, Membership, Organization
from .fulfillment import Redemption


class ClinicBill(Entity):
    clinic = models.ForeignKey(Clinic, on_delete=models.PROTECT, related_name="bills")
    cycle = models.CharField(max_length=16)
    period_end = models.DateField()
    issued_on = models.DateField()
    due_at = models.DateTimeField()
    status = models.CharField(max_length=16, default="open")
    total_cents = models.PositiveBigIntegerField()
    received_cents = models.PositiveBigIntegerField(default=0)
    settled_at = models.DateTimeField(null=True)
    dispute = models.BooleanField(default=False)
    contract_version = models.UUIDField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["clinic", "issued_on"], name="clinic_bill_issue_date")]


class ClinicBillLine(Entity):
    bill = models.ForeignKey(ClinicBill, on_delete=models.PROTECT, related_name="lines")
    redemption = models.ForeignKey(Redemption, on_delete=models.PROTECT, related_name="bill_lines")
    amount_cents = models.PositiveBigIntegerField()
    active = models.BooleanField(default=True)
    removed_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["redemption"], condition=Q(active=True), name="one_active_clinic_bill_line")]


class BillRevision(Entity):
    bill = models.ForeignKey(ClinicBill, on_delete=models.PROTECT, related_name="revisions")
    revision = models.PositiveIntegerField()
    snapshot = models.JSONField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["bill", "revision"], name="bill_revision")]


class ClinicReceipt(Entity):
    bill = models.ForeignKey(ClinicBill, on_delete=models.PROTECT, related_name="receipts")
    bill_version = models.PositiveIntegerField()
    amount_cents = models.PositiveBigIntegerField()
    paid_at = models.DateTimeField()
    payer = EncryptedTextField()
    reference = EncryptedTextField()
    reference_index = models.CharField(max_length=64)
    attachment_ids = models.JSONField(default=list)
    status = models.CharField(max_length=16, default="pending")
    submitted_by = models.ForeignKey(Membership, on_delete=models.PROTECT)
    reviewed_by = models.ForeignKey(Membership, null=True, on_delete=models.PROTECT, related_name="clinic_receipt_reviews")
    reviewed_at = models.DateTimeField(null=True)
    reason = EncryptedTextField(default="")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["bill"], condition=Q(status="pending"), name="one_pending_clinic_receipt")]


class PaymentAttempt(Entity):
    bill = models.ForeignKey(ClinicBill, on_delete=models.PROTECT, related_name="payment_attempts")
    bill_version = models.PositiveIntegerField()
    number = models.CharField(max_length=32, unique=True)
    amount_cents = models.PositiveBigIntegerField()
    method = models.CharField(max_length=16)
    status = models.CharField(max_length=16, default="creating")
    gateway_transaction = models.CharField(max_length=100, blank=True)
    gateway_payload = EncryptedJSONField(default=dict)
    created_by = models.ForeignKey(Membership, on_delete=models.PROTECT)
    error_code = models.CharField(max_length=80, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["bill"], condition=Q(status__in=["creating", "pending", "unknown"]), name="one_unresolved_payment")]


class ReceiptLedger(Entity):
    reference_index = models.CharField(max_length=64, unique=True)
    kind = models.CharField(max_length=16)
    source_id = models.UUIDField()
    bill = models.ForeignKey(ClinicBill, null=True, on_delete=models.PROTECT)
    amount_cents = models.PositiveBigIntegerField()
    received_at = models.DateTimeField()
    anomaly = models.CharField(max_length=80, blank=True)


class PartnerBill(Entity):
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    month = models.DateField()
    issued_on = models.DateField()
    due_at = models.DateTimeField()
    total_cents = models.PositiveBigIntegerField()
    status = models.CharField(max_length=24, default="pending_confirmation")
    confirmed_by = models.ForeignKey(Membership, null=True, on_delete=models.PROTECT, related_name="partner_bill_confirmations")
    confirmed_at = models.DateTimeField(null=True)
    confirmed_version = models.PositiveIntegerField(null=True)
    received_by = models.ForeignKey(Membership, null=True, on_delete=models.PROTECT, related_name="partner_receipt_confirmations")
    received_at = models.DateTimeField(null=True)
    actual_received_on = models.DateField(null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["organization", "month"], name="partner_month_unique")]


class PartnerBillLine(Entity):
    bill = models.ForeignKey(PartnerBill, on_delete=models.PROTECT, related_name="lines")
    redemption = models.ForeignKey(Redemption, on_delete=models.PROTECT, related_name="partner_lines")
    kind = models.CharField(max_length=16)
    amount_cents = models.PositiveBigIntegerField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["redemption", "kind"], name="partner_share_once")]


class PartnerPayment(Entity):
    bill = models.OneToOneField(PartnerBill, on_delete=models.PROTECT, related_name="payment")
    amount_cents = models.PositiveBigIntegerField()
    bill_version = models.PositiveIntegerField()
    paid_at = models.DateTimeField()
    reference = EncryptedTextField()
    reference_index = models.CharField(max_length=64, unique=True)
    attachment_ids = models.JSONField(default=list)
    actor = models.ForeignKey(Membership, on_delete=models.PROTECT)


class FinanceFeedback(Entity):
    clinic_bill = models.ForeignKey(ClinicBill, null=True, on_delete=models.PROTECT, related_name="feedback")
    partner_bill = models.ForeignKey(PartnerBill, null=True, on_delete=models.PROTECT, related_name="feedback")
    kind = models.CharField(max_length=24)
    message = EncryptedTextField()
    response = EncryptedTextField(default="")
    status = models.CharField(max_length=16, default="open")
    actor = models.ForeignKey(Membership, on_delete=models.PROTECT)
    responded_by = models.ForeignKey(Membership, null=True, on_delete=models.PROTECT, related_name="finance_responses")
    responded_at = models.DateTimeField(null=True)
