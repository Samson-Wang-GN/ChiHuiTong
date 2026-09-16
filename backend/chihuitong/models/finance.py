from django.db import models
from django.db.models import Q

from chihuitong.crypto import EncryptedJSONField, EncryptedTextField

from .catalog import Clinic
from .core import Entity, Membership, Organization
from .fulfillment import Redemption


class ClinicBill(Entity):
    clinic = models.ForeignKey(Clinic, null=True, on_delete=models.PROTECT, related_name="bills")
    cooperation = models.ForeignKey("ClinicCooperation", null=True, on_delete=models.PROTECT, related_name="bills")
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
        constraints = [
            models.UniqueConstraint(fields=["clinic", "issued_on"], name="clinic_bill_issue_date"),
            models.UniqueConstraint(fields=["cooperation", "issued_on"], name="cooperation_bill_issue_date"),
            models.CheckConstraint(condition=Q(clinic__isnull=False, cooperation__isnull=True) | Q(clinic__isnull=True, cooperation__isnull=False), name="bill_one_debtor"),
        ]


class ClinicBillLine(Entity):
    bill = models.ForeignKey(ClinicBill, on_delete=models.PROTECT, related_name="lines")
    redemption = models.ForeignKey(Redemption, on_delete=models.PROTECT, related_name="bill_lines")
    amount_cents = models.PositiveBigIntegerField()
    active = models.BooleanField(default=True)
    removed_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["redemption"], condition=Q(active=True), name="one_active_clinic_bill_line"
            )
        ]


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
    reviewed_by = models.ForeignKey(
        Membership, null=True, on_delete=models.PROTECT, related_name="clinic_receipt_reviews"
    )
    reviewed_at = models.DateTimeField(null=True)
    reason = EncryptedTextField(default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["bill"], condition=Q(status="pending"), name="one_pending_clinic_receipt"
            )
        ]


class PaymentAttempt(Entity):
    bill = models.ForeignKey(ClinicBill, null=True, on_delete=models.PROTECT, related_name="payment_attempts")
    instant_order = models.ForeignKey("InstantRedemptionOrder", null=True, on_delete=models.PROTECT, related_name="payment_attempts")
    bill_version = models.PositiveIntegerField()
    number = models.CharField(max_length=32, unique=True)
    amount_cents = models.PositiveBigIntegerField()
    method = models.CharField(max_length=16)
    status = models.CharField(max_length=16, default="creating")
    gateway_transaction = models.CharField(max_length=100, blank=True)
    gateway_payload = EncryptedJSONField(default=dict)
    created_by = models.ForeignKey(Membership, on_delete=models.PROTECT)
    error_code = models.CharField(max_length=80, blank=True)
    appid = models.CharField(max_length=32, blank=True)
    mchid = models.CharField(max_length=32, blank=True)
    expires_at = models.DateTimeField(null=True)
    request_key = models.CharField(max_length=128, blank=True)
    payer_openid = EncryptedTextField(default="")
    preparation_count = models.PositiveIntegerField(default=1)
    preparation_started_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(bill__isnull=False, instant_order__isnull=True) | Q(bill__isnull=True, instant_order__isnull=False), name="payment_one_target"),
            models.UniqueConstraint(fields=["instant_order"], condition=Q(status__in=["creating", "pending", "unknown"]), name="one_unresolved_instant_payment"),
            models.UniqueConstraint(
                fields=["created_by", "request_key"],
                condition=~Q(request_key=""),
                name="payment_request_once",
            ),
            models.UniqueConstraint(
                fields=["bill"],
                condition=Q(status__in=["creating", "pending", "unknown"]),
                name="one_unresolved_payment",
            ),
        ]


class PaymentNotification(Entity):
    notification_id = models.CharField(max_length=100, unique=True)
    attempt = models.ForeignKey(PaymentAttempt, on_delete=models.PROTECT)
    payload = EncryptedJSONField()
    body_digest = models.CharField(max_length=64)
    status = models.CharField(max_length=16, default="pending")
    processed_at = models.DateTimeField(null=True)


class ReceiptLedger(Entity):
    reference_index = models.CharField(max_length=64, unique=True)
    kind = models.CharField(max_length=16)
    source_id = models.UUIDField()
    bill = models.ForeignKey(ClinicBill, null=True, on_delete=models.PROTECT)
    instant_order = models.ForeignKey("InstantRedemptionOrder", null=True, on_delete=models.PROTECT, related_name="receipts")
    amount_cents = models.PositiveBigIntegerField()
    received_at = models.DateTimeField()
    anomaly = models.CharField(max_length=80, blank=True)


class InstantRedemptionOrder(Entity):
    appointment = models.ForeignKey("Appointment", on_delete=models.PROTECT, related_name="instant_orders")
    cooperation = models.ForeignKey("ClinicCooperation", on_delete=models.PROTECT)
    agreement = models.ForeignKey("ClinicAgreement", on_delete=models.PROTECT)
    created_by = models.ForeignKey(Membership, on_delete=models.PROTECT)
    status = models.CharField(max_length=16, default="pending")
    amount_cents = models.PositiveBigIntegerField()
    snapshot = models.JSONField()
    appointment_version = models.PositiveIntegerField()
    redemption = models.OneToOneField(Redemption, null=True, on_delete=models.PROTECT, related_name="instant_order")
    paid_at = models.DateTimeField(null=True)
    error_code = models.CharField(max_length=80, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["appointment"], condition=Q(status__in=["pending", "paid", "completed"]), name="one_active_instant_order"),
            models.CheckConstraint(condition=Q(status__in=["pending", "paid", "completed", "closed"]), name="instant_order_state"),
        ]


class PartnerBill(Entity):
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    month = models.DateField()
    issued_on = models.DateField()
    due_at = models.DateTimeField()
    total_cents = models.PositiveBigIntegerField()
    status = models.CharField(max_length=24, default="pending_confirmation")
    confirmed_by = models.ForeignKey(
        Membership, null=True, on_delete=models.PROTECT, related_name="partner_bill_confirmations"
    )
    confirmed_at = models.DateTimeField(null=True)
    confirmed_version = models.PositiveIntegerField(null=True)
    received_by = models.ForeignKey(
        Membership,
        null=True,
        on_delete=models.PROTECT,
        related_name="partner_receipt_confirmations",
    )
    received_at = models.DateTimeField(null=True)
    actual_received_on = models.DateField(null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization", "month"], name="partner_month_unique")
        ]


class PartnerBillLine(Entity):
    bill = models.ForeignKey(PartnerBill, on_delete=models.PROTECT, related_name="lines")
    redemption = models.ForeignKey(
        Redemption, on_delete=models.PROTECT, related_name="partner_lines"
    )
    kind = models.CharField(max_length=16)
    amount_cents = models.PositiveBigIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["redemption", "kind"], name="partner_share_once")
        ]


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
    clinic_bill = models.ForeignKey(
        ClinicBill, null=True, on_delete=models.PROTECT, related_name="feedback"
    )
    partner_bill = models.ForeignKey(
        PartnerBill, null=True, on_delete=models.PROTECT, related_name="feedback"
    )
    kind = models.CharField(max_length=24)
    message = EncryptedTextField()
    response = EncryptedTextField(default="")
    status = models.CharField(max_length=16, default="open")
    actor = models.ForeignKey(Membership, on_delete=models.PROTECT)
    responded_by = models.ForeignKey(
        Membership, null=True, on_delete=models.PROTECT, related_name="finance_responses"
    )
    responded_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(clinic_bill__isnull=False, partner_bill__isnull=True)
                    | Q(clinic_bill__isnull=True, partner_bill__isnull=False)
                ),
                name="feedback_exactly_one_bill",
            )
        ]
