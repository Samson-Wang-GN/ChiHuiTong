from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .api import StrictSerializer, paginated, validated
from .api_catalog import VersionInput
from .errors import require
from .exports import excel_response
from .identity import request_actor
from .models import Card, CardRange, ImportFormat, ImportRow, Outbox, PurchaseReceipt
from .services import imports, sales
from .services.common import RESOURCE_KINDS, audit, idempotent


def command(request, actor, operation, payload, callback):
    return idempotent(
        actor.membership.id,
        operation,
        request.headers.get("Idempotency-Key", ""),
        payload,
        callback,
    )


def order_projection(order):
    data = {
        key: getattr(order, key)
        for key in [
            "source_name",
            "mode",
            "entry",
            "quantity",
            "unit_price_cents",
            "total_cents",
            "received_cents",
            "status",
            "validity_days",
            "units_per_card",
            "product_snapshot",
            "version",
            "reason",
            "shipment",
            "refund",
            "issue_failure_code",
        ]
    }
    data.update(
        {
            key: str(getattr(order, key))
            for key in ["id", "organization_id", "responsible_id", "product_id", "source_brand_id"]
        }
    )
    data["import_batch_id"] = str(order.import_batch_id) if order.import_batch_id else None
    number_range = CardRange.objects.filter(order=order).first()
    data["number_range"] = (
        {"first": str(number_range.first_number), "last": str(number_range.last_number)}
        if number_range
        else None
    )
    if order.status in {"issuing", "issue_failed"}:
        job = (
            Outbox.objects.filter(
                kind="sales.issue", dedup_key__startswith=f"sales.issue:{order.id}:"
            )
            .order_by("-created_at")
            .first()
        )
        data["processing"] = (
            {
                "job_id": str(job.id),
                "status": job.status,
                "attempts": job.attempts,
                "last_error_code": job.last_error_code,
            }
            if job
            else None
        )
    else:
        data["processing"] = None
    return data


class SalesInput(StrictSerializer):
    product_id = serializers.UUIDField()
    source_brand_id = serializers.UUIDField()
    mode = serializers.ChoiceField(choices=["named", "physical"])
    entry = serializers.ChoiceField(choices=["single", "excel", "quantity"])
    unit_price_cents = serializers.IntegerField(min_value=0, max_value=100000000, default=0)
    quantity = serializers.IntegerField(min_value=1, max_value=100000, required=False)
    rows = serializers.ListField(
        child=serializers.JSONField(), min_length=1, max_length=1, required=False
    )
    import_batch_id = serializers.UUIDField(required=False)
    responsible_id = serializers.UUIDField(required=False)
    units_per_card = serializers.IntegerField(min_value=1, max_value=10000, default=1)


class ReviewInput(VersionInput):
    approved = serializers.BooleanField()
    reason = serializers.CharField(max_length=500)


class SalesReview(ReviewInput):
    validity_days = serializers.IntegerField(min_value=1, max_value=36500, required=False)


class ReceiptInput(VersionInput):
    amount_cents = serializers.IntegerField(min_value=1)
    paid_at = serializers.DateTimeField()
    payer = serializers.CharField(max_length=200)
    reference = serializers.CharField(max_length=160)
    attachment_ids = serializers.ListField(
        child=serializers.CharField(max_length=36), min_length=1, max_length=20
    )


class StopInput(VersionInput):
    action = serializers.ChoiceField(choices=["cancel", "stop"])
    reason = serializers.CharField(max_length=500)


class RefundInput(VersionInput):
    amount_cents = serializers.IntegerField(min_value=1)
    refunded_at = serializers.DateTimeField()
    reference = serializers.CharField(max_length=160)
    attachment_ids = serializers.ListField(
        child=serializers.CharField(max_length=36), min_length=1, max_length=20
    )
    reason = serializers.CharField(max_length=500)


class ShipmentInput(VersionInput):
    recipient = serializers.CharField(max_length=100)
    phone = serializers.CharField(max_length=40)
    address = serializers.CharField(max_length=500)
    carrier = serializers.CharField(max_length=100)
    tracking_number = serializers.CharField(max_length=160)


def receipt_projection(item):
    return {
        "id": str(item.id),
        "order_id": str(item.order_id),
        "amount_cents": item.amount_cents,
        "paid_at": item.paid_at.isoformat(),
        "payer": item.payer,
        "reference": item.reference,
        "attachment_ids": item.attachment_ids,
        "status": item.status,
        "reason": item.reason,
        "version": item.version,
    }


@api_view(["GET", "POST"])
def orders(request):
    actor = request_actor(request)
    if request.method == "POST":
        data = validated(SalesInput, request)
        return Response(
            command(
                request,
                actor,
                "sales.create",
                data,
                lambda: order_projection(sales.create_order(actor, **data)),
            ),
            status=201,
        )
    qs = sales.visible_orders(actor)
    if request.query_params.get("product_id"):
        qs = qs.filter(
            product_id=serializers.UUIDField().run_validation(request.query_params["product_id"])
        )
    return paginated(
        request,
        qs,
        order_projection,
        states=[
            "pending_payment",
            "payment_review",
            "pending_approval",
            "issuing",
            "issue_failed",
            "issued",
            "rejected",
            "cancel_pending",
            "stop_pending",
            "cancelled",
            "stopped",
        ],
    )


@api_view(["GET"])
def order_detail(request, order_id):
    return Response(order_projection(sales.get_order(request_actor(request), order_id)))


@api_view(["GET"])
def order_rows(request, order_id):
    order = sales.get_order(request_actor(request), order_id)
    return paginated(
        request,
        order.rows.all(),
        lambda row: {
            "id": str(row.id),
            "row_number": row.row_number,
            "raw": row.raw,
            "normalized": row.normalized,
            "customer_id": str(row.customer_id) if row.customer_id else None,
            "quantity": row.quantity,
        },
        status_field=None,
    )


@api_view(["POST"])
def order_action(request, order_id, action):
    actor = request_actor(request)
    sales.get_order(actor, order_id)
    operations = {
        "review": (SalesReview, sales.request_approval, True),
        "stop": (StopInput, sales.request_stop, False),
        "stop-review": (ReviewInput, sales.review_stop, True),
        "refund": (RefundInput, sales.register_refund, True),
        "shipment": (ShipmentInput, sales.register_shipment, True),
    }
    require(action in operations, "not_found", "操作不存在", 404)
    schema, service, platform_only = operations[action]
    if platform_only:
        actor.require_platform()
    data = validated(schema, request)
    return Response(
        command(
            request,
            actor,
            f"sales.{action}",
            {"order_id": str(order_id), **data},
            lambda: order_projection(service(actor, order_id, **data)),
        )
    )


@api_view(["GET", "POST"])
def receipts(request, order_id):
    actor = request_actor(request)
    order = sales.get_order(actor, order_id)
    if request.method == "POST":
        data = validated(ReceiptInput, request)
        return Response(
            command(
                request,
                actor,
                "sales.receipt",
                {"order_id": str(order_id), **data},
                lambda: receipt_projection(sales.submit_receipt(actor, order_id, **data)),
            ),
            status=201,
        )
    return paginated(
        request,
        PurchaseReceipt.objects.filter(order=order),
        receipt_projection,
        states=["pending", "approved", "rejected"],
    )


@api_view(["POST"])
def receipt_review(request, receipt_id):
    actor, data = request_actor(request), validated(ReviewInput, request)
    actor.require_platform()
    return Response(
        command(
            request,
            actor,
            "sales.receipt_review",
            {"receipt_id": str(receipt_id), **data},
            lambda: receipt_projection(sales.review_receipt(actor, receipt_id, **data)),
        )
    )


def card_projection(card):
    return {
        "id": str(card.id),
        "serial": str(card.serial),
        "customer_id": str(card.customer_id) if card.customer_id else None,
        "status": card.status,
        "frozen": card.frozen,
        "activated_at": card.activated_at.isoformat() if card.activated_at else None,
        "version": card.version,
    }


@api_view(["GET"])
def cards(request, order_id):
    order = sales.get_order(request_actor(request), order_id)
    return paginated(
        request,
        Card.objects.filter(order=order),
        card_projection,
        states=["unclaimed", "active", "void"],
    )


class FreezeInput(StrictSerializer):
    frozen = serializers.BooleanField()
    reason = serializers.CharField(max_length=500)


@api_view(["POST"])
def freeze_card(request, card_id):
    actor, data = request_actor(request), validated(FreezeInput, request)
    actor.require_platform()
    return Response(
        command(
            request,
            actor,
            "card.freeze",
            {"card_id": str(card_id), **data},
            lambda: card_projection(sales.freeze_card(actor, card_id, **data)),
        )
    )


@api_view(["POST"])
def export_cards(request, order_id):
    actor = request_actor(request)
    order = sales.get_order(actor, order_id)
    require(
        request.data == {"confirmed": True},
        "confirmation_required",
        "卡片激活凭证为敏感资料，请确认安全保管",
        400,
    )
    require(
        order.mode == "physical" and order.status == "issued",
        "invalid_export",
        "仅已开卡实体订单支持制卡下载",
    )
    query = order.cards.all()
    state = request.query_params.get("status", "all")
    require(
        state in {"all", "unclaimed", "active", "void"}, "invalid_status", "卡片状态不合法", 400
    )
    if state != "all":
        query = query.filter(status=state)
    audit(actor, order, "sales.cards_exported", count=query.count(), status=state)
    return excel_response(
        ["卡号", "推广产品外部名称", "权益来源", "激活凭证", "状态"],
        (
            (
                str(card.serial),
                order.product_snapshot["external_name"],
                order.source_name,
                card.credential if card.status == "unclaimed" and not card.frozen else "不可激活",
                card.status,
            )
            for card in query.order_by("serial").iterator()
        ),
        filename="physical-cards.xlsx",
    )


def import_projection(batch):
    return {
        "id": str(batch.id),
        "asset_id": str(batch.asset_id),
        "status": batch.status,
        "version": batch.version,
        "sheets": batch.sheets,
        "configuration": batch.configuration,
        "mapping_digest": batch.mapping_digest,
        "total_rows": batch.total_rows,
        "processed_rows": batch.processed_rows,
        "error_rows": batch.error_rows,
        "total_cards": batch.total_cards,
        "failure_code": batch.failure_code,
    }


class ImportInput(StrictSerializer):
    asset_id = serializers.UUIDField()


@api_view(["GET", "POST"])
def import_list(request):
    actor = request_actor(request)
    if request.method == "POST":
        data = validated(ImportInput, request)
        return Response(
            command(
                request,
                actor,
                "import.create",
                data,
                lambda: import_projection(imports.create_import(actor, **data)),
            ),
            status=201,
        )
    return paginated(
        request,
        imports.visible_imports(actor),
        import_projection,
        states=["queued", "mapping", "validating", "validated", "confirmed", "failed"],
    )


@api_view(["GET"])
def import_detail(request, batch_id):
    batch = imports.get_import(request_actor(request), batch_id)
    return Response({**import_projection(batch), "preview": batch.preview,
                     "recommendation": imports.recommend_import(batch) if batch.status == "mapping" else None})


class MappingInput(VersionInput):
    sheet = serializers.CharField(max_length=100)
    header_row = serializers.IntegerField(min_value=1, max_value=20)
    mapping = serializers.DictField(child=serializers.IntegerField(min_value=0, max_value=199))
    quantity_mode = serializers.ChoiceField(choices=["column", "uniform"])
    uniform_quantity = serializers.IntegerField(min_value=1, max_value=100000, required=False)


@api_view(["POST"])
def import_mapping(request, batch_id):
    actor, data = request_actor(request), validated(MappingInput, request)
    return Response(
        command(
            request,
            actor,
            "import.mapping",
            {"batch_id": str(batch_id), **data},
            lambda: import_projection(imports.configure_import(actor, batch_id, **data)),
        )
    )


class ConfirmInput(VersionInput):
    mapping_digest = serializers.CharField(max_length=64)


@api_view(["POST"])
def import_confirm(request, batch_id):
    actor, data = request_actor(request), validated(ConfirmInput, request)
    return Response(
        command(
            request,
            actor,
            "import.confirm",
            {"batch_id": str(batch_id), **data},
            lambda: import_projection(imports.confirm_import(actor, batch_id, **data)),
        )
    )


@api_view(["GET"])
def import_rows(request, batch_id):
    batch = imports.get_import(request_actor(request), batch_id)
    return paginated(
        request,
        ImportRow.objects.filter(batch=batch),
        lambda row: {
            "id": str(row.id),
            "row_number": row.row_number,
            "raw": row.raw,
            "normalized": row.normalized,
            "errors": row.errors,
            "status": row.status,
        },
        states=["valid", "invalid"],
    )


@api_view(["GET"])
def import_errors(request, batch_id):
    actor = request_actor(request)
    batch = imports.get_import(actor, batch_id)
    query = batch.rows.filter(status="invalid").order_by("row_number")
    audit(actor, batch, "import.errors_exported", count=query.count())
    return excel_response(
        ["原始行号", "客户姓名", "手机号", "开卡数量", "异常原因"],
        (
            (
                row.row_number,
                str(row.raw.get("name", "")),
                str(row.raw.get("phone", "")),
                str(row.raw.get("quantity", "")),
                "；".join(error["message"] for error in row.errors),
            )
            for row in query.iterator()
        ),
        filename="import-errors.xlsx",
    )


class FormatInput(StrictSerializer):
    batch_id = serializers.UUIDField()
    name = serializers.CharField(max_length=100)


@api_view(["GET", "POST"])
def import_formats(request):
    actor = request_actor(request)
    require(actor.organization.kind in RESOURCE_KINDS, "forbidden", "仅资源方可管理导入格式", 403)
    if request.method == "POST":
        item = imports.save_format(actor, **validated(FormatInput, request))
        return Response(
            {"id": str(item.id), "name": item.name, "structure": item.structure}, status=201
        )
    return paginated(
        request,
        ImportFormat.objects.filter(organization=actor.organization),
        lambda item: {"id": str(item.id), "name": item.name, "structure": item.structure},
        status_field=None,
    )


class SuggestInput(StrictSerializer):
    sheet = serializers.CharField(max_length=100)
    header_row = serializers.IntegerField(min_value=1, max_value=20)
    format_id = serializers.UUIDField(required=False)


@api_view(["POST"])
def import_suggest(request, batch_id):
    actor = request_actor(request)
    batch = imports.get_import(actor, batch_id)
    data = validated(SuggestInput, request)
    preview = batch.preview.get(data["sheet"], [])
    require(data["header_row"] <= len(preview), "invalid_header", "表头行不存在", 400)
    stored = None
    if data.get("format_id"):
        stored = ImportFormat.objects.filter(
            pk=data["format_id"], organization=actor.organization
        ).first()
        require(stored, "not_found", "导入格式不存在", 404)
    return Response(imports.suggest_mapping(preview[data["header_row"] - 1], stored))
