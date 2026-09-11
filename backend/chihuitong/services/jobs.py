import logging
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from chihuitong.errors import BusinessError
from chihuitong.models import ImportBatch, Outbox

logger = logging.getLogger("chihuitong.jobs")


def run_one():
    now = timezone.now()
    with transaction.atomic():
        job = (
            Outbox.objects.select_for_update(skip_locked=True)
            .filter(available_at__lte=now)
            .filter(Q(status="pending") | Q(status="running", locked_until__lt=now))
            .order_by("created_at")
            .first()
        )
        if not job:
            return False
        job.status, job.locked_until = "running", now + timedelta(minutes=10)
        job.attempts += 1
        job.save(update_fields=["status", "locked_until", "attempts"])
        attempt = job.attempts
    try:
        from .imports import inspect_import, validate_import

        handlers = {"excel.inspect": inspect_import, "excel.validate": validate_import}
        if job.kind not in handlers:
            raise BusinessError("unknown_job_kind", "任务类型尚未配置", 409)
        handlers[job.kind](job.payload["batch_id"], job.payload["version"])
    except Exception as exc:
        code = exc.code if isinstance(exc, BusinessError) else type(exc).__name__
        logger.warning("job_failed id=%s code=%s attempt=%s", job.id, code, attempt)
        terminal = isinstance(exc, BusinessError) or attempt >= 5
        with transaction.atomic():
            current = Outbox.objects.select_for_update().get(pk=job.id)
            if current.attempts != attempt:
                return True
            current.status = "failed" if terminal else "pending"
            current.last_error_code = code[:80]
            current.available_at = timezone.now() + timedelta(seconds=min(3600, 30 * 2**attempt))
            current.save(update_fields=["status", "last_error_code", "available_at"])
            if terminal and job.kind.startswith("excel."):
                ImportBatch.objects.filter(
                    pk=job.payload["batch_id"], version=job.payload["version"]
                ).update(status="failed", failure_code=code[:80])
        return True
    Outbox.objects.filter(pk=job.id, attempts=attempt, status="running").update(
        status="done", locked_until=None
    )
    return True
