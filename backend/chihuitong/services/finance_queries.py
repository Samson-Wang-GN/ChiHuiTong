from django.db.models import Case, CharField, Exists, OuterRef, Q, Value, When
from django.utils import timezone

from chihuitong.models import ClinicReceipt, PartnerBill, PaymentAttempt

from .common import RESOURCE_KINDS
from .finance import visible_clinic_bills


def clinic_bills_with_status(actor):
    return (
        visible_clinic_bills(actor)
        .annotate(
            has_receipt=Exists(
                ClinicReceipt.objects.filter(bill_id=OuterRef("pk"), status="pending")
            ),
            has_payment=Exists(
                PaymentAttempt.objects.filter(
                    bill_id=OuterRef("pk"), status__in=["creating", "pending", "unknown"]
                )
            ),
        )
        .annotate(
            display_status=Case(
                When(status__in=["settled", "cancelled", "no_payment"], then="status"),
                When(due_at__lt=timezone.now(), then=Value("overdue")),
                When(dispute=True, then=Value("disputed")),
                When(Q(has_receipt=True) | Q(has_payment=True), then=Value("payment_review")),
                default=Value("pending_payment"),
                output_field=CharField(),
            )
        )
    )


def partner_bills(actor):
    if actor.platform:
        return PartnerBill.objects.select_related("organization").all()
    actor.require_admin()
    return PartnerBill.objects.select_related("organization").filter(
        organization=actor.organization
    )


def iso(value):
    return value.isoformat() if value else None


def clinic_bill_projection(bill):
    from .finance import effective_bill_status

    return {
        "id": str(bill.id),
        "clinic_id": str(bill.clinic_id),
        "clinic_name": bill.clinic.organization.name,
        "cycle": bill.cycle,
        "issued_on": iso(bill.issued_on),
        "period_end": iso(bill.period_end),
        "due_at": iso(bill.due_at),
        "status": getattr(bill, "display_status", None) or effective_bill_status(bill),
        "ledger_status": bill.status,
        "total_cents": bill.total_cents,
        "received_cents": bill.received_cents,
        "remaining_cents": bill.total_cents - bill.received_cents,
        "settled_at": iso(bill.settled_at),
        "version": bill.version,
        "dispute": bill.dispute,
        "contract_version": str(bill.contract_version),
    }


def partner_bill_projection(bill):
    return {
        "id": str(bill.id),
        "organization_id": str(bill.organization_id),
        "organization_name": bill.organization.name,
        "month": iso(bill.month),
        "issued_on": iso(bill.issued_on),
        "due_at": iso(bill.due_at),
        "total_cents": bill.total_cents,
        "status": bill.status,
        "version": bill.version,
        "confirmed_at": iso(bill.confirmed_at),
        "received_at": iso(bill.received_at),
        "actual_received_on": iso(bill.actual_received_on),
    }


def transaction_projection(actor, record):
    appointment = record.appointment
    customer = appointment.customer
    product = appointment.benefit.product
    phone = customer.phone
    # Clinics need their appointment contact; other channels get a masked customer phone.
    if not actor.platform and actor.organization.kind not in RESOURCE_KINDS | {"clinic"}:
        phone = phone[:3] + "****" + phone[-4:] if len(phone) == 11 else ""
    result = {
        "id": str(record.id),
        "appointment_id": str(appointment.id),
        "customer_number": customer.number,
        "customer_name": customer.name,
        "phone": phone,
        "product_id": str(product.id),
        "internal_name": record.snapshot.get(
            "internal_name",
            appointment.benefit.card.order.product_snapshot.get(
                "internal_name", product.internal_name
            ),
        ),
        "external_name": record.snapshot.get(
            "external_name",
            appointment.benefit.card.order.product_snapshot.get(
                "external_name", product.external_name
            ),
        ),
        "clinic_id": str(appointment.clinic_id),
        "clinic_name": appointment.clinic.organization.name,
        "source_name": appointment.benefit.card.order.source_name,
        "scheduled_at": iso(appointment.scheduled_at),
        "redeemed_at": iso(record.created_at),
        "units": record.units,
        "status": record.status,
        "clinic_settled": record.settled_at is not None,
        "settled_at": iso(record.settled_at),
        "reversed_at": iso(record.reversed_at),
        "version": record.version,
    }
    if actor.platform or actor.organization.kind in {"clinic", "channel"}:
        result["fee_cents"] = record.fee_cents
    if actor.platform or actor.organization.kind in RESOURCE_KINDS:
        result["resource_cents"] = record.resource_cents
    if actor.platform or actor.organization.kind == "channel":
        result["channel_cents"] = record.channel_cents
    if actor.platform:
        result["platform_cents"] = record.platform_cents
        result["allocation_snapshot"] = record.snapshot
    return result


def receipt_projection(receipt):
    return {
        "id": str(receipt.id),
        "bill_id": str(receipt.bill_id),
        "bill_version": receipt.bill_version,
        "amount_cents": receipt.amount_cents,
        "paid_at": iso(receipt.paid_at),
        "payer": receipt.payer,
        "reference": receipt.reference,
        "attachment_ids": receipt.attachment_ids,
        "status": receipt.status,
        "reason": receipt.reason,
        "version": receipt.version,
    }


def feedback_projection(item):
    return {
        "id": str(item.id),
        "message": item.message,
        "response": item.response,
        "status": item.status,
        "version": item.version,
        "created_at": iso(item.created_at),
        "responded_at": iso(item.responded_at),
    }
