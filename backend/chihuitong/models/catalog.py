from django.db import models
from django.db.models import F, Q

from chihuitong.crypto import EncryptedJSONField, EncryptedTextField

from .core import Account, Entity, Membership, Organization


class Product(Entity):
    internal_name = models.CharField(max_length=160, unique=True)
    external_name = models.CharField(max_length=160)
    status = models.CharField(max_length=16, default="active")
    product_type = models.CharField(max_length=20, default="service")
    usage_rules = models.TextField()
    redemption_units = models.PositiveIntegerField(default=1)
    fee_cents = models.PositiveBigIntegerField()
    validity_days = models.PositiveIntegerField(default=180)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(redemption_units__gt=0), name="positive_redemption_units"),
            models.CheckConstraint(condition=Q(validity_days__gt=0), name="positive_validity_days"),
            models.CheckConstraint(condition=Q(status__in=["active", "disabled"]), name="product_state"),
        ]


class ProductRevision(Entity):
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="revisions")
    revision = models.PositiveIntegerField()
    snapshot = models.JSONField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["product", "revision"], name="product_revision")]


class SourceBrand(Entity):
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    name = models.CharField(max_length=160)
    status = models.CharField(max_length=16, default="active")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["organization", "name"], name="brand_per_resource")]


class FileAsset(Entity):
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    uploaded_by = models.ForeignKey(Account, on_delete=models.PROTECT)
    original_name = EncryptedTextField()
    storage_key = models.CharField(max_length=100, unique=True)
    content_type = models.CharField(max_length=100)
    size = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64)
    purpose = models.CharField(max_length=30)
    status = models.CharField(max_length=16, default="ready")


class Clinic(Entity):
    organization = models.OneToOneField(Organization, on_delete=models.PROTECT, related_name="clinic")
    channel = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="managed_clinics")
    responsible = models.ForeignKey(Membership, on_delete=models.PROTECT, related_name="assigned_clinics")
    profile = EncryptedJSONField(default=dict)
    profile_version = models.PositiveIntegerField(default=0)
    review_status = models.CharField(max_length=16, default="draft")
    service_status = models.CharField(max_length=16, default="offline")
    confirmation_hours = models.PositiveIntegerField(default=24)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(confirmation_hours__gt=0), name="positive_confirm_hours"),
            models.CheckConstraint(condition=Q(service_status__in=["online", "offline", "paused", "exited"]), name="clinic_service_state"),
        ]


class AttachmentLink(Entity):
    asset = models.ForeignKey(FileAsset, on_delete=models.PROTECT, related_name="links")
    object_type = models.CharField(max_length=40)
    object_id = models.UUIDField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["asset", "object_type", "object_id"], name="unique_attachment_link")]


class ClinicProfileChange(Entity):
    clinic = models.ForeignKey(Clinic, on_delete=models.PROTECT, related_name="profile_changes")
    base_version = models.PositiveIntegerField()
    before = EncryptedJSONField(default=dict)
    after = EncryptedJSONField(default=dict)
    submitted_by = models.ForeignKey(Membership, on_delete=models.PROTECT)
    reviewed_by = models.ForeignKey(Membership, null=True, on_delete=models.PROTECT, related_name="profile_reviews")
    status = models.CharField(max_length=16, default="pending")
    reason = EncryptedTextField(default="")
    due_at = models.DateTimeField()
    reviewed_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["clinic"], condition=Q(status="pending"), name="one_pending_profile")]


class Contract(Entity):
    organization = models.OneToOneField(Organization, on_delete=models.PROTECT, related_name="contract")
    kind = models.CharField(max_length=16, choices=[("resource", "平台—资源方"), ("channel", "平台—渠道"), ("clinic", "平台—渠道—门诊")])
    number = models.CharField(max_length=80, unique=True)


class ContractVersion(Entity):
    contract = models.ForeignKey(Contract, on_delete=models.PROTECT, related_name="versions")
    revision = models.PositiveIntegerField()
    status = models.CharField(max_length=16, default="draft")
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    channel = models.ForeignKey(Organization, null=True, on_delete=models.PROTECT, related_name="tripartite_versions")
    settlement_cycle = models.CharField(max_length=16, default="monthly")
    contact = EncryptedJSONField(default=dict)
    attachment_ids = models.JSONField(default=list)
    submitted_by = models.ForeignKey(Membership, on_delete=models.PROTECT)
    submitted_at = models.DateTimeField(null=True)
    due_at = models.DateTimeField(null=True)
    reviewed_by = models.ForeignKey(Membership, null=True, on_delete=models.PROTECT, related_name="contract_reviews")
    reviewed_at = models.DateTimeField(null=True)
    reason = EncryptedTextField(default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["contract", "revision"], name="contract_revision"),
            models.UniqueConstraint(fields=["contract"], condition=Q(status="pending"), name="one_pending_contract"),
            models.CheckConstraint(condition=Q(ends_at__gt=F("starts_at")), name="contract_dates"),
            models.CheckConstraint(condition=Q(settlement_cycle__in=["weekly", "monthly"]), name="contract_cycle"),
        ]


class ContractProduct(Entity):
    contract_version = models.ForeignKey(ContractVersion, on_delete=models.PROTECT, related_name="products")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    mode = models.CharField(max_length=16, default="percent")
    value = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    status = models.CharField(max_length=16, default="active")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["contract_version", "product"], name="one_product_per_version"),
            models.CheckConstraint(condition=Q(value__gte=0), name="nonnegative_split"),
            models.CheckConstraint(condition=Q(mode__in=["percent", "amount"]), name="split_mode"),
            models.CheckConstraint(condition=Q(mode="amount") | Q(value__lte=100), name="split_percent_limit"),
        ]


class ContractProductRevision(Entity):
    term = models.ForeignKey(ContractProduct, on_delete=models.PROTECT)
    revision = models.PositiveIntegerField()
    snapshot = models.JSONField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["term", "revision"], name="term_revision")]


class ClinicProduct(Entity):
    clinic = models.ForeignKey(Clinic, on_delete=models.PROTECT, related_name="products")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    status = models.CharField(max_length=16, default="offline")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["clinic", "product"], name="one_clinic_product")]
