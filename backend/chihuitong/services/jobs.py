import logging
import uuid
from datetime import timedelta

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from chihuitong.errors import BusinessError
from chihuitong.models import ImportBatch, Outbox, SalesOrder

from .common import audit

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
        job.claim_token = uuid.uuid4()
        job.attempts += 1
        job.save(update_fields=["status", "locked_until", "attempts", "claim_token"])
        attempt = job.attempts
    try:
        from .imports import inspect_import, validate_import

        if job.kind in {"excel.inspect", "excel.validate"}:
            handler = inspect_import if job.kind == "excel.inspect" else validate_import
            handler(job.payload["batch_id"], job.payload["version"])
        elif job.kind == "payment.notification":
            from .payments import process_notification

            process_notification(job.payload["notification_id"])
        elif job.kind == "sms.business":
            from .notifications import send_business

            send_business(job)
        elif job.kind == "sales.issue":
            from .sales import process_issuance

            process_issuance(job.payload)
        elif job.kind == "appointment.deadline":
            from .appointments import process_deadline

            process_deadline(job.payload["appointment_id"])
        elif job.kind == "billing.clinic":
            from datetime import date

            from .finance import generate_clinic_bill

            generate_clinic_bill(
                job.payload["clinic_id"], issued_on=date.fromisoformat(job.payload["issued_on"])
            )
        elif job.kind == "billing.partner":
            from datetime import date

            from .finance import generate_partner_bills

            generate_partner_bills(issued_on=date.fromisoformat(job.payload["issued_on"]))
        elif job.kind == "payment.reconcile":
            from .payments import reconcile

            payment = reconcile(job.payload["attempt_id"])
            if payment.status not in {"success", "closed"}:
                raise BusinessError("payment_unresolved", "支付等待查单", 503)
        else:
            raise BusinessError("unknown_job_kind", "任务类型尚未配置", 409)
    except Exception as exc:
        code = exc.code if isinstance(exc, BusinessError) else type(exc).__name__
        logger.warning("job_failed id=%s code=%s attempt=%s", job.id, code, attempt)
        terminal = (isinstance(exc, BusinessError) and exc.status < 500) or attempt >= 5
        with transaction.atomic():
            if job.kind == "sales.issue":
                SalesOrder.objects.select_for_update().get(pk=job.payload["order_id"])
            if job.kind in {"excel.inspect", "excel.validate"}:
                ImportBatch.objects.select_for_update().get(pk=job.payload["batch_id"])
            current = Outbox.objects.select_for_update().get(pk=job.id)
            if current.claim_token != job.claim_token:
                return True
            current.status = "failed" if terminal else "pending"
            current.last_error_code = code[:80]
            current.available_at = timezone.now() + timedelta(seconds=min(3600, 30 * 2**attempt))
            current.save(update_fields=["status", "last_error_code", "available_at"])
            if terminal and job.kind.startswith("excel."):
                ImportBatch.objects.filter(
                    pk=job.payload["batch_id"], version=job.payload["version"]
                ).update(status="failed", failure_code=code[:80])
            if terminal and job.kind == "sales.issue":
                updated = SalesOrder.objects.filter(
                    pk=job.payload["order_id"], status="issuing", version=job.payload["version"]
                ).update(
                    status="issue_failed",
                    issue_failure_code=code[:80],
                    version=F("version") + 1,
                )
                if updated:
                    audit(
                        None,
                        SalesOrder.objects.get(pk=job.payload["order_id"]),
                        "sales.issuance_failed",
                        error_code=code[:80],
                        job_id=str(job.id),
                    )
        return True
    Outbox.objects.filter(pk=job.id, claim_token=job.claim_token, status="running").update(
        status="done", locked_until=None
    )
    return True
