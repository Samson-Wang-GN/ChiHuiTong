import hashlib
import json
from dataclasses import dataclass

from django.db import connection, transaction

from chihuitong.errors import require
from chihuitong.models import AuditEvent, IdempotencyRecord, Membership

RESOURCE_KINDS = {"insurance", "bank", "broker"}


@dataclass(frozen=True)
class Actor:
    membership: Membership
    request_id: object = None

    @property
    def organization(self):
        return self.membership.organization

    @property
    def account(self):
        return self.membership.account

    @property
    def platform(self):
        return self.organization.kind == "platform" and self.membership.role == "admin"

    def require_admin(self):
        require(self.membership.role == "admin", "forbidden", "此操作仅管理员可处理", 403)

    def require_platform(self):
        require(self.platform, "forbidden", "此操作仅平台管理员可处理", 403)


def audit(actor, obj, action, *, reason="", **metadata):
    # Metadata deliberately contains only identifiers/statuses/field names, never form contents.
    return AuditEvent.objects.create(
        actor=actor.account if actor else None,
        membership=actor.membership if actor else None,
        organization=actor.organization if actor else None,
        object_type=obj._meta.model_name,
        object_id=obj.pk,
        action=action,
        reason=reason,
        metadata=metadata,
        request_id=actor.request_id if actor else None,
    )


def check_version(obj, expected):
    require(
        isinstance(expected, int) and not isinstance(expected, bool) and obj.version == expected,
        "stale_version",
        "记录已更新，请刷新后重新操作",
    )


def advance(obj, *fields):
    obj.version += 1
    obj.save(update_fields=[*fields, "version", "updated_at"])


def advisory_lock(namespace, key):
    """Transaction-scoped PG lock for records not yet created; no global lock/PII in SQL."""
    require(connection.in_atomic_block, "transaction_required", "事务未建立", 500)
    value = int.from_bytes(hashlib.sha256(f"{namespace}:{key}".encode()).digest()[:8], signed=True)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [value])


@transaction.atomic
def idempotent(actor_id, operation, key, payload, callback):
    require(
        isinstance(key, str) and 8 <= len(key) <= 128, "idempotency_key", "请提供幂等请求编号", 400
    )
    fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
    advisory_lock(operation, f"{actor_id}:{key}")
    old = IdempotencyRecord.objects.filter(actor_id=actor_id, operation=operation, key=key).first()
    if old:
        require(
            old.request_digest == fingerprint,
            "idempotency_conflict",
            "同一请求编号不可用于不同内容",
        )
        return old.result
    result = callback()
    IdempotencyRecord.objects.create(
        actor_id=actor_id, operation=operation, key=key, request_digest=fingerprint, result=result
    )
    return result
