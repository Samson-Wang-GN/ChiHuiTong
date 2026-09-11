import uuid

from django.db import models
from django.db.models import Q

from chihuitong.crypto import EncryptedJSONField, EncryptedTextField


class Entity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        abstract = True


class Organization(Entity):
    class Kind(models.TextChoices):
        PLATFORM = "platform", "平台"
        INSURANCE = "insurance", "保险公司"
        BANK = "bank", "银行"
        BROKER = "broker", "经纪代理公司"
        CHANNEL = "channel", "门诊渠道公司"
        CLINIC = "clinic", "口腔门诊"

    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    status = models.CharField(max_length=16, default="active")
    details = EncryptedJSONField(default=dict)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["kind"], condition=Q(kind="platform"), name="one_platform"
            ),
            models.CheckConstraint(
                condition=Q(status__in=["active", "disabled", "pending", "rejected"]),
                name="organization_state",
            ),
        ]


class Account(Entity):
    phone = EncryptedTextField()
    phone_index = models.CharField(max_length=64, unique=True)
    name = EncryptedTextField()
    active = models.BooleanField(default=True)

    @property
    def is_authenticated(self):
        return True


class Membership(Entity):
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="memberships")
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    role = models.CharField(max_length=16, choices=[("admin", "管理员"), ("staff", "业务员/员工")])
    active = models.BooleanField(default=True)
    platform_created = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["account", "organization"], name="one_membership"),
            models.CheckConstraint(condition=Q(role__in=["admin", "staff"]), name="member_role"),
            models.CheckConstraint(
                condition=Q(platform_created=False) | Q(role="admin"), name="initial_admin_role"
            ),
        ]


class LoginChallenge(Entity):
    phone_index = models.CharField(max_length=64, unique=True)
    code_digest = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    sent_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    consumed = models.BooleanField(default=False)
    delivered = models.BooleanField(default=False)


class RateBucket(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    window = models.DateTimeField()
    count = models.PositiveIntegerField(default=0)


class Session(Entity):
    token_digest = models.CharField(max_length=64, unique=True)
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    audience = models.CharField(max_length=20, default="web")
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True)


class AuditEvent(models.Model):
    id = models.BigAutoField(primary_key=True)
    occurred_at = models.DateTimeField(auto_now_add=True)
    actor = models.ForeignKey(Account, null=True, on_delete=models.PROTECT)
    membership = models.ForeignKey(Membership, null=True, on_delete=models.PROTECT)
    organization = models.ForeignKey(Organization, null=True, on_delete=models.PROTECT)
    object_type = models.CharField(max_length=80)
    object_id = models.UUIDField()
    action = models.CharField(max_length=80)
    reason = EncryptedTextField(default="")
    metadata = models.JSONField(default=dict)
    request_id = models.UUIDField(null=True)
    actor_role = models.CharField(max_length=16, blank=True)
    actor_name = EncryptedTextField(default="")
    organization_name = models.CharField(max_length=200, blank=True)

    class Meta:
        indexes = [models.Index(fields=["object_type", "object_id", "id"])]


class IdempotencyRecord(models.Model):
    id = models.BigAutoField(primary_key=True)
    actor_id = models.UUIDField()
    operation = models.CharField(max_length=80)
    key = models.CharField(max_length=128)
    request_digest = models.CharField(max_length=64)
    result = EncryptedJSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["actor_id", "operation", "key"], name="operation_retry")
        ]


class Outbox(Entity):
    kind = models.CharField(max_length=40)
    dedup_key = models.CharField(max_length=200, unique=True)
    payload = EncryptedJSONField(default=dict)
    status = models.CharField(max_length=16, default="pending")
    attempts = models.PositiveIntegerField(default=0)
    available_at = models.DateTimeField()
    locked_until = models.DateTimeField(null=True)
    claim_token = models.UUIDField(null=True)
    last_error_code = models.CharField(max_length=80, blank=True)

    class Meta:
        indexes = [models.Index(fields=["status", "available_at"])]


class BusinessCalendar(models.Model):
    date = models.DateField(primary_key=True)
    working = models.BooleanField()
    note = models.CharField(max_length=200, blank=True)
