from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .api import paginated, validated
from .api_catalog import VersionInput
from .api_sales import ReceiptInput, ReviewInput, command
from .errors import require
from .exports import excel_response
from .identity import request_actor
from .models import PartnerPayment
from .services import finance
from .services import finance_queries as queries
from .services.common import audit

LINE_RELATED = [
    "redemption__appointment__customer",
    "redemption__appointment__clinic__organization",
    "redemption__appointment__benefit__product",
    "redemption__appointment__benefit__card__order",
]


@api_view(["GET"])
def clinic_bills(request):
    actor = request_actor(request)
    qs = queries.clinic_bills_with_status(actor)
    if request.query_params.get("clinic_id"):
        qs = qs.filter(
            clinic_id=serializers.UUIDField().run_validation(request.query_params["clinic_id"])
        )
    return paginated(
        request,
        qs,
        queries.clinic_bill_projection,
        status_field="display_status",
        states=[
            "pending_payment",
            "payment_review",
            "disputed",
            "overdue",
            "settled",
            "cancelled",
            "no_payment",
        ],
    )


@api_view(["GET"])
def clinic_bill_detail(request, bill_id):
    actor = request_actor(request)
    bill = finance.get_bill(actor, bill_id)
    return Response(
        {
            **queries.clinic_bill_projection(bill),
            "revisions": [
                {
                    "version": item.revision,
                    "snapshot": item.snapshot,
                    "created_at": queries.iso(item.created_at),
                }
                for item in bill.revisions.order_by("revision")
            ],
            "feedback": [
                queries.feedback_projection(item) for item in bill.feedback.order_by("created_at")
            ],
        }
    )


def clinic_line_projection(actor, line):
    return {
        "id": str(line.id),
        "active": line.active,
        "amount_cents": line.amount_cents,
        "removed_at": queries.iso(line.removed_at),
        "transaction": queries.transaction_projection(actor, line.redemption),
    }


@api_view(["GET"])
def clinic_bill_lines(request, bill_id):
    actor = request_actor(request)
    bill = finance.get_bill(actor, bill_id)
    return paginated(
        request,
        bill.lines.select_related(*LINE_RELATED),
        lambda line: clinic_line_projection(actor, line),
        status_field="active",
        states=[True, False],
    )


def export_lines(actor, bill, query, filename):
    audit(actor, bill, "bill.lines_exported", count=query.count())
    return excel_response(
        [
            "交易编号",
            "预约编号",
            "客户编号",
            "客户姓名",
            "手机号",
            "推广产品",
            "权益来源",
            "门诊",
            "预约时间",
            "核销时间",
            "核销数量",
            "门诊已结清",
            "门诊结清时间",
            "本单金额（分）",
            "交易状态",
            "已从本单移除",
        ],
        (
            export_row(actor, line)
            for line in query.select_related(*LINE_RELATED).order_by("created_at", "id").iterator()
        ),
        filename=filename,
    )


def export_row(actor, line):
    row = queries.transaction_projection(actor, line.redemption)
    return [
        row["id"],
        row["appointment_id"],
        row["customer_number"],
        row["customer_name"],
        row["phone"],
        row["internal_name"],
        row["source_name"],
        row["clinic_name"],
        row["scheduled_at"],
        row["redeemed_at"],
        row["units"],
        "是" if row["clinic_settled"] else "否",
        row["settled_at"],
        line.amount_cents,
        row["status"],
        "是" if not getattr(line, "active", True) else "否",
    ]


@api_view(["GET"])
def clinic_bill_export(request, bill_id):
    actor = request_actor(request)
    bill = finance.get_bill(actor, bill_id)
    state = request.query_params.get("status", "active")
    require(state in {"active", "disabled", "all"}, "invalid_status", "明细状态不合法", 400)
    qs = bill.lines.all()
    if state != "all":
        qs = qs.filter(active=state == "active")
    return export_lines(actor, bill, qs, "clinic-bill.xlsx")


@api_view(["GET", "POST"])
def clinic_receipts(request, bill_id):
    actor = request_actor(request)
    bill = finance.get_bill(actor, bill_id)
    if request.method == "POST":
        data = validated(ReceiptInput, request)
        return Response(
            command(
                request,
                actor,
                "clinic.receipt",
                {"bill_id": str(bill_id), **data},
                lambda: queries.receipt_projection(finance.submit_receipt(actor, bill_id, **data)),
            ),
            status=201,
        )
    return paginated(
        request,
        bill.receipts.all(),
        queries.receipt_projection,
        states=["pending", "approved", "rejected"],
    )


@api_view(["POST"])
def receipt_review(request, receipt_id):
    actor = request_actor(request)
    actor.require_platform()
    data = validated(ReviewInput, request)
    return Response(
        command(
            request,
            actor,
            "clinic.receipt_review",
            {"receipt_id": str(receipt_id), **data},
            lambda: queries.receipt_projection(finance.review_receipt(actor, receipt_id, **data)),
        )
    )


@api_view(["GET"])
def partner_bills(request):
    actor = request_actor(request)
    qs = queries.partner_bills(actor)
    if request.query_params.get("organization_id"):
        qs = qs.filter(
            organization_id=serializers.UUIDField().run_validation(
                request.query_params["organization_id"]
            )
        )
    return paginated(
        request,
        qs,
        queries.partner_bill_projection,
        states=[
            "pending_confirmation",
            "pending_payment",
            "pending_receipt",
            "completed",
            "no_payment",
        ],
    )


@api_view(["GET"])
def partner_bill_detail(request, bill_id):
    actor = request_actor(request)
    bill = finance.get_partner_bill(actor, bill_id)
    payment = PartnerPayment.objects.filter(bill=bill).first()
    return Response(
        {
            **queries.partner_bill_projection(bill),
            "payment": {
                "id": str(payment.id),
                "amount_cents": payment.amount_cents,
                "paid_at": queries.iso(payment.paid_at),
                "reference": payment.reference,
                "attachment_ids": payment.attachment_ids,
            }
            if payment
            else None,
            "feedback": [
                queries.feedback_projection(item) for item in bill.feedback.order_by("created_at")
            ],
        }
    )


def partner_line_projection(actor, line):
    return {
        "id": str(line.id),
        "bill_id": str(line.bill_id),
        "amount_cents": line.amount_cents,
        "status": line.bill.status,
        "kind": line.kind,
        "transaction": queries.transaction_projection(actor, line.redemption),
    }


@api_view(["GET"])
def partner_bill_lines(request, bill_id=None):
    actor = request_actor(request)
    # Staff deliberately use the separate own-details collection, never whole statement totals.
    if bill_id:
        finance.get_partner_bill(actor, bill_id)
    qs = finance.visible_partner_lines(actor).select_related(*LINE_RELATED)
    if bill_id:
        qs = qs.filter(bill_id=bill_id)
    return paginated(
        request,
        qs,
        lambda line: partner_line_projection(actor, line),
        status_field="bill__status",
        states=[
            "pending_confirmation",
            "pending_payment",
            "pending_receipt",
            "completed",
            "no_payment",
        ],
    )


@api_view(["GET"])
def partner_bill_export(request, bill_id):
    actor = request_actor(request)
    bill = finance.get_partner_bill(actor, bill_id)
    return export_lines(
        actor, bill, finance.visible_partner_lines(actor).filter(bill=bill), "partner-bill.xlsx"
    )


@api_view(["GET"])
def own_partner_export(request):
    actor = request_actor(request)
    qs = finance.visible_partner_lines(actor)
    state = request.query_params.get("status", "all")
    require(
        state
        in {
            "all",
            "pending_confirmation",
            "pending_payment",
            "pending_receipt",
            "completed",
            "no_payment",
        },
        "invalid_status",
        "结算状态不合法",
        400,
    )
    if state != "all":
        qs = qs.filter(bill__status=state)
    return export_lines(actor, actor.organization, qs, "own-settlement-details.xlsx")


class ConfirmationInput(VersionInput):
    confirmed = serializers.BooleanField()


class PartnerPaymentInput(ConfirmationInput):
    amount_cents = serializers.IntegerField(min_value=1)
    paid_at = serializers.DateTimeField()
    reference = serializers.CharField(max_length=160)
    attachment_ids = serializers.ListField(
        child=serializers.CharField(max_length=36), min_length=1, max_length=20
    )


class PartnerReceiptInput(ConfirmationInput):
    actual_received_on = serializers.DateField()


@api_view(["POST"])
def partner_bill_action(request, bill_id, action):
    actor = request_actor(request)
    finance.get_partner_bill(actor, bill_id, operate=True)
    actions = {
        "confirm": (ConfirmationInput, finance.confirm_partner_bill),
        "pay": (PartnerPaymentInput, finance.pay_partner_bill),
        "receive": (PartnerReceiptInput, finance.receive_partner_bill),
    }
    require(action in actions, "not_found", "操作不存在", 404)
    schema, operation = actions[action]
    data = validated(schema, request)
    return Response(
        command(
            request,
            actor,
            f"partner_bill.{action}",
            {"bill_id": str(bill_id), **data},
            lambda: queries.partner_bill_projection(operation(actor, bill_id, **data)),
        )
    )


class FeedbackInput(VersionInput):
    message = serializers.CharField(max_length=2000)


class ResponseInput(VersionInput):
    response = serializers.CharField(max_length=2000)


@api_view(["POST"])
def bill_feedback(request, bill_id, partner=False):
    actor = request_actor(request)
    data = validated(FeedbackInput, request)
    return Response(
        command(
            request,
            actor,
            "bill.feedback",
            {"bill_id": str(bill_id), "partner": partner, **data},
            lambda: queries.feedback_projection(
                finance.submit_feedback(actor, bill_id, partner=partner, **data)
            ),
        ),
        status=201,
    )


@api_view(["POST"])
def feedback_response(request, feedback_id):
    actor = request_actor(request)
    actor.require_platform()
    data = validated(ResponseInput, request)
    return Response(
        command(
            request,
            actor,
            "bill.feedback_response",
            {"feedback_id": str(feedback_id), **data},
            lambda: queries.feedback_projection(
                finance.respond_feedback(actor, feedback_id, **data)
            ),
        )
    )
