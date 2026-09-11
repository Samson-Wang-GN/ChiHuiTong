import uuid

from django.db import models
from django.db.models import F, Q

from chihuitong.crypto import EncryptedJSONField, EncryptedTextField

from .catalog import FileAsset, Product, SourceBrand
from .core import Entity, Membership, Organization


def customer_number():
    return "C" + uuid.uuid4().hex.upper()


class Customer(Entity):
    number = models.CharField(max_length=40, unique=True, default=customer_number, editable=False)
    phone = EncryptedTextField()
    phone_index = models.CharField(max_length=64, unique=True)
    name = EncryptedTextField()
    profile = EncryptedJSONField(default=dict)
    registered_at = models.DateTimeField(null=True)


class CustomerSource(Entity):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="sources")
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "organization"], name="customer_source_relation"
            )
        ]


class ImportFormat(Entity):
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    name = models.CharField(max_length=100)
    structure = models.JSONField(default=dict)


class ImportBatch(Entity):
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    created_by = models.ForeignKey(Membership, on_delete=models.PROTECT)
    asset = models.ForeignKey(FileAsset, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, default="uploaded")
    configuration = models.JSONField(default=dict)
    sheets = models.JSONField(default=list)
    preview = EncryptedJSONField(default=dict)
    mapping_digest = models.CharField(max_length=64, blank=True)
    confirmed_at = models.DateTimeField(null=True)
    total_rows = models.PositiveIntegerField(default=0)
    processed_rows = models.PositiveIntegerField(default=0)
    error_rows = models.PositiveIntegerField(default=0)
    total_cards = models.PositiveIntegerField(default=0)
    failure_code = models.CharField(max_length=80, blank=True)


class ImportRow(Entity):
    batch = models.ForeignKey(ImportBatch, on_delete=models.PROTECT, related_name="rows")
    row_number = models.PositiveIntegerField()
    raw = EncryptedJSONField(default=dict)
    normalized = EncryptedJSONField(default=dict)
    errors = models.JSONField(default=list)
    status = models.CharField(max_length=16, default="valid")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["batch", "row_number"], name="import_original_row")
        ]


class SalesOrder(Entity):
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    responsible = models.ForeignKey(Membership, on_delete=models.PROTECT)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    source_brand = models.ForeignKey(SourceBrand, on_delete=models.PROTECT)
    import_batch = models.OneToOneField(ImportBatch, null=True, on_delete=models.PROTECT)
    mode = models.CharField(max_length=16)
    entry = models.CharField(max_length=16)
    quantity = models.PositiveIntegerField()
    unit_price_cents = models.PositiveBigIntegerField(default=0)
    total_cents = models.PositiveBigIntegerField()
    received_cents = models.PositiveBigIntegerField(default=0)
    status = models.CharField(max_length=24, default="draft")
    previous_status = models.CharField(max_length=24, blank=True)
    validity_days = models.PositiveIntegerField(default=180)
    units_per_card = models.PositiveIntegerField(default=1)
    product_snapshot = models.JSONField(default=dict)
    source_name = models.CharField(max_length=160)
    submitted_at = models.DateTimeField(null=True)
    approved_at = models.DateTimeField(null=True)
    reviewed_by = models.ForeignKey(
        Membership, null=True, on_delete=models.PROTECT, related_name="sales_reviews"
    )
    reason = EncryptedTextField(default="")
    shipment = EncryptedJSONField(default=dict)
    refund = EncryptedJSONField(default=dict)
    issue_failure_code = models.CharField(max_length=80, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="sales_quantity_positive"),
            models.CheckConstraint(condition=Q(units_per_card__gt=0), name="card_units_positive"),
            models.CheckConstraint(
                condition=Q(total_cents=F("quantity") * F("unit_price_cents")),
                name="sales_total_consistent",
            ),
            models.CheckConstraint(condition=Q(mode__in=["named", "physical"]), name="sales_mode"),
        ]


class SalesRow(Entity):
    order = models.ForeignKey(SalesOrder, on_delete=models.PROTECT, related_name="rows")
    row_number = models.PositiveIntegerField()
    raw = EncryptedJSONField(default=dict)
    normalized = EncryptedJSONField(default=dict)
    customer = models.ForeignKey(Customer, null=True, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["order", "row_number"], name="sales_original_row")
        ]


class PurchaseReceipt(Entity):
    order = models.ForeignKey(SalesOrder, on_delete=models.PROTECT, related_name="receipts")
    amount_cents = models.PositiveBigIntegerField()
    paid_at = models.DateTimeField()
    payer = EncryptedTextField()
    reference = EncryptedTextField()
    reference_index = models.CharField(max_length=64)
    attachment_ids = models.JSONField(default=list)
    status = models.CharField(max_length=16, default="pending")
    submitted_by = models.ForeignKey(Membership, on_delete=models.PROTECT)
    reviewed_by = models.ForeignKey(
        Membership, null=True, on_delete=models.PROTECT, related_name="purchase_reviews"
    )
    reviewed_at = models.DateTimeField(null=True)
    reason = EncryptedTextField(default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["order"], condition=Q(status="pending"), name="one_pending_purchase_receipt"
            ),
            models.UniqueConstraint(
                fields=["reference_index"],
                condition=Q(status="approved"),
                name="purchase_receipt_reference",
            ),
        ]


class CardSequence(models.Model):
    name = models.CharField(max_length=30, primary_key=True)
    next_number = models.PositiveBigIntegerField(default=100000000000)


class CardRange(Entity):
    order = models.OneToOneField(SalesOrder, on_delete=models.PROTECT, related_name="number_range")
    first_number = models.PositiveBigIntegerField(unique=True)
    last_number = models.PositiveBigIntegerField(unique=True)


class Card(Entity):
    order = models.ForeignKey(SalesOrder, on_delete=models.PROTECT, related_name="cards")
    row = models.ForeignKey(SalesRow, null=True, on_delete=models.PROTECT)
    serial = models.PositiveBigIntegerField(unique=True)
    credential = EncryptedTextField()
    credential_digest = models.CharField(max_length=64, unique=True)
    customer = models.ForeignKey(Customer, null=True, on_delete=models.PROTECT)
    status = models.CharField(max_length=16, default="unclaimed")
    frozen = models.BooleanField(default=False)
    activated_at = models.DateTimeField(null=True)
    voided_at = models.DateTimeField(null=True)


class Benefit(Entity):
    card = models.OneToOneField(Card, on_delete=models.PROTECT, related_name="benefit")
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="benefits")
    source = models.ForeignKey(CustomerSource, on_delete=models.PROTECT)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    total = models.PositiveIntegerField()
    pending = models.PositiveIntegerField(default=0)
    available = models.PositiveIntegerField(default=0)
    reserved = models.PositiveIntegerField(default=0)
    used = models.PositiveIntegerField(default=0)
    restoring = models.PositiveIntegerField(default=0)
    voided = models.PositiveIntegerField(default=0)
    activated_at = models.DateTimeField(null=True)
    expires_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    total=F("pending")
                    + F("available")
                    + F("reserved")
                    + F("used")
                    + F("restoring")
                    + F("voided")
                ),
                name="benefit_quantity_conservation",
            )
        ]


class DomainEvent(models.Model):
    id = models.BigAutoField(primary_key=True)
    occurred_at = models.DateTimeField()
    recorded_at = models.DateTimeField(auto_now_add=True)
    card = models.ForeignKey(Card, on_delete=models.PROTECT)
    kind = models.CharField(max_length=40)
    object_id = models.UUIDField()
    payload = models.JSONField(default=dict)

    class Meta:
        indexes = [
            models.Index(fields=["card", "occurred_at", "id"]),
            models.Index(fields=["object_id", "kind", "occurred_at"]),
        ]
