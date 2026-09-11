"""Idempotent tick. Intended to run every minute in an independent worker."""
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from chihuitong.errors import BusinessError
from chihuitong.models import Appointment, Clinic, ClinicBill, ContractVersion, Membership, Outbox, PartnerBill

from .common import advisory_lock
from .contracts import current_contract
from .notifications import notify_members


def enqueue(kind, key, payload):
    _, created = Outbox.objects.get_or_create(kind=kind, dedup_key=key,
        defaults={"payload": payload, "available_at": timezone.now()})
    return int(created)


def tick():
    now, day = timezone.now(), timezone.localdate()
    created = 0
    # A tick queues small independently retryable units; it never holds a whole-platform write transaction.
    appointments = Appointment.objects.filter(
        Q(status="pending", pending_deadline__lte=now)
        | Q(status="success", scheduled_at__lte=now - timedelta(hours=24))
        | Q(reschedules__status="pending", reschedules__expires_at__lte=now)
    ).distinct()
    for item in appointments.order_by("created_at").iterator(chunk_size=200):
        phase = "pending" if item.status == "pending" else "72" if item.scheduled_at and item.scheduled_at <= now - timedelta(hours=72) else "24"
        expired_change = item.reschedules.filter(status="pending", expires_at__lte=now).first()
        if expired_change:
            phase += ":change:" + expired_change.id.hex
        created += enqueue("appointment.deadline", f"deadline:{item.id}:{item.version}:{phase}", {"appointment_id": str(item.id)})
    if day.weekday() == 0 or day.day == 1:
        # Old unbilled redemptions are part of each generated bill, not just this period's visits.
        clinics = Clinic.objects.filter(appointments__redemptions__status="active", appointments__redemptions__settled_at__isnull=True).distinct()
        for clinic in clinics.iterator(chunk_size=200):
            try:
                contract = current_contract(clinic.organization_id, stock=True, channel_id=clinic.channel_id)
            except BusinessError:
                # The generation job records a visible failure; don't silently invent contract terms.
                cycle = "unknown"
            else:
                cycle = contract.settlement_cycle
            if cycle == "unknown" or (cycle == "weekly" and day.weekday() == 0) or (cycle == "monthly" and day.day == 1):
                created += enqueue("billing.clinic", f"clinic-bill:{clinic.id}:{day}", {"clinic_id": str(clinic.id), "issued_on": day.isoformat()})
    if day.day == 1:
        created += enqueue("billing.partner", f"partner-bills:{day}", {"issued_on": day.isoformat()})
    for bill in ClinicBill.objects.filter(status="open").select_related("clinic__responsible__account", "clinic__organization").iterator(chunk_size=200):
        overdue = now > bill.due_at
        template = "bill.overdue" if overdue else "bill.reminder"
        phase = "overdue" if overdue else day.isoformat()
        parameters = {"bill_number": bill.id.hex[-8:].upper(), "amount": f"{Decimal(bill.total_cents-bill.received_cents)/100:.2f}",
                      "due_date": timezone.localtime(bill.due_at).date().isoformat()}
        targets = {"clinic": bill.clinic.profile.get("business_phone", ""),
                   "channel": bill.clinic.responsible.account.phone}
        for party, phone in targets.items():
            created += enqueue("sms.business", f"bill-sms:{bill.id}:{party}:{phase}",
                {"template": template, "bill_id": str(bill.id), "phone": phone, "parameters": parameters})
        title = "门诊账单已逾期，请核对付款" if overdue else "门诊账单待付款"
        members = Membership.objects.filter(Q(organization_id=bill.clinic.organization_id, role="admin")
            | Q(pk=bill.clinic.responsible_id))
        notify_members(members, kind=template, obj=bill, title=title, key=f"bill:{bill.id}:{day}")
    for bill in PartnerBill.objects.exclude(status__in=["completed", "no_payment"]).iterator(chunk_size=200):
        if bill.status == "pending_payment":
            members = Membership.objects.filter(organization__kind="platform", role="admin")
            title = "合作方已确认结算单，请登记线下付款"
        else:
            members = Membership.objects.filter(organization_id=bill.organization_id, role="admin")
            title = "请核对合作结算单" if bill.status == "pending_confirmation" else "平台已付款，请核对实际到账"
        notify_members(members, kind="partner_bill." + bill.status, obj=bill, title=title,
                       key=f"partner:{bill.id}:{bill.status}:{day}")
    expiring = ContractVersion.objects.filter(status="approved", starts_at__lte=now,
        ends_at__gte=now, ends_at__lte=now + timedelta(days=30)).select_related("contract")
    for version in expiring.iterator(chunk_size=200):
        try:
            selected = current_contract(version.contract.organization_id, stock=True)
        except BusinessError:
            continue
        if selected.id != version.id:
            continue
        org_id = version.contract.organization_id
        members = Membership.objects.filter(organization_id=org_id, role="admin")
        if version.contract.kind == "clinic":
            clinic = Clinic.objects.filter(organization_id=org_id).first()
            if clinic:
                members = Membership.objects.filter(Q(organization_id=org_id, role="admin") | Q(pk=clinic.responsible_id))
        notify_members(members, kind="contract.expiring", obj=version.contract, title="合作合同将于30天内到期，请办理续签",
                       key=f"contract-expiry:{version.id}:{day}")
    return {"queued": created, "at": now.isoformat()}


@transaction.atomic
def retry_job(actor, job_id, *, reason):
    from chihuitong.errors import require
    from .common import advance, audit
    actor.require_platform()
    advisory_lock("job_retry", str(job_id))
    job = Outbox.objects.select_for_update().filter(pk=job_id).first()
    require(job, "not_found", "任务不存在", 404)
    require(job.status == "failed" and isinstance(reason, str) and reason.strip(),
            "invalid_retry", "仅失败任务可以重试，请填写原因", 400)
    job.status, job.available_at, job.locked_until, job.attempts = "pending", timezone.now(), None, 0
    advance(job, "status", "available_at", "locked_until", "attempts")
    audit(actor, job, "job.retried", reason=reason)
    return job
