from datetime import datetime

from django.db import transaction
from django.utils import timezone

from chihuitong.crypto import digest
from chihuitong.errors import require
from chihuitong.models import Benefit, Card, CardRange, CardSequence, CustomerSource, ImportBatch, Membership, Product, PurchaseReceipt, SalesOrder, SalesRow, SourceBrand

from .catalog import product_snapshot
from .common import RESOURCE_KINDS, advance, advisory_lock, audit, check_version
from .contracts import current_contract
from .customers import event, match_preview, new_credential, normalize_customer, resolve_customer
from .files import link_files, validate_attachment_ids


def visible_orders(actor):
    qs = SalesOrder.objects.select_related("organization", "product", "source_brand", "responsible")
    if actor.platform:
        return qs
    if actor.organization.kind not in RESOURCE_KINDS:
        return qs.none()
    qs = qs.filter(organization=actor.organization)
    if actor.membership.role != "admin":
        qs = qs.filter(responsible=actor.membership)
    return qs


def get_order(actor, order_id, *, lock=False):
    qs = visible_orders(actor)
    if lock:
        qs = qs.select_for_update(of=("self",))
    order = qs.filter(pk=order_id).first()
    require(order, "not_found", "销售订单不存在或无权访问", 404)
    return order


def validate_authorization(order):
    require(order.organization.status == "active", "organization_disabled", "资源方已停用")
    current_contract(order.organization_id, product_id=order.product_id)
    require(order.product.status == "active", "product_disabled", "产品已停用")
    require(order.source_brand.organization_id == order.organization_id and order.source_brand.status == "active", "invalid_source", "来源展示名当前不可用")


def validate_rows(rows):
    require(isinstance(rows, list) and 0 < len(rows) <= 10000, "row_limit", "名单须为1～10000行，可分批继续", 400)
    seen, normalized = set(), []
    for row in rows:
        value = normalize_customer(row)
        require(value["phone"] not in seen, "duplicate_phone", "同一名单存在重复手机号，请核对后重传", 400)
        seen.add(value["phone"])
        match_preview(value)
        normalized.append(value)
    return normalized


@transaction.atomic
def create_order(actor, *, product_id, source_brand_id, mode, entry, unit_price_cents=0, quantity=None, rows=None, import_batch_id=None, responsible_id=None, units_per_card=1):
    require(actor.organization.kind in RESOURCE_KINDS, "forbidden", "仅客户资源方可以提交采购订单", 403)
    require(mode in {"named", "physical"} and entry in {"single", "excel", "quantity"}, "invalid_mode", "销售方式不合法", 400)
    require(type(unit_price_cents) is int and 0 <= unit_price_cents <= 100000000, "invalid_price", "单卡采购价必须为非负整分", 400)
    require(type(units_per_card) is int and 1 <= units_per_card <= 10000, "invalid_units", "每卡权益份数不合法", 400)
    responsible = Membership.objects.filter(pk=responsible_id or actor.membership.id, organization=actor.organization, active=True, account__active=True).first()
    require(responsible and (actor.membership.role == "admin" or responsible.id == actor.membership.id), "invalid_responsible", "请选择本机构有效业务员；业务员仅可负责本人订单", 403)
    product = Product.objects.select_for_update().filter(pk=product_id, status="active").first()
    source = SourceBrand.objects.filter(pk=source_brand_id, organization=actor.organization, status="active").first()
    require(product and source, "invalid_product_source", "产品或来源展示名不可用", 400)
    current_contract(actor.organization.id, product_id=product.id)
    batch = None
    normalized, raw_rows, row_numbers = [], [], []
    if mode == "physical":
        require(entry == "quantity" and not rows and not import_batch_id, "physical_no_excel", "不记名实体卡只填写数量，不上传客户名单", 400)
    elif entry == "single":
        require(rows and len(rows) == 1 and not import_batch_id and quantity is None, "invalid_single", "单客销售必须填写一名客户，不另设总数量", 400)
        normalized = validate_rows(rows)
        raw_rows, row_numbers = rows, [1]
        quantity = sum(row["quantity"] for row in normalized)
    else:
        require(entry == "excel" and not rows and quantity is None, "invalid_import", "批量销售请使用已确认的Excel名单", 400)
        batch = ImportBatch.objects.select_for_update().filter(pk=import_batch_id, organization=actor.organization, status="confirmed").first()
        require(batch and (actor.membership.role == "admin" or batch.created_by_id == actor.membership.id), "import_unconfirmed", "请先完成本机构名单校验并确认列映射", 400)
        require(not SalesOrder.objects.filter(import_batch=batch).exists(), "import_consumed", "该导入名单已提交订单")
        entries = list(batch.rows.order_by("row_number"))
        normalized = validate_rows([row.normalized for row in entries])
        raw_rows, row_numbers = [row.raw for row in entries], [row.row_number for row in entries]
        quantity = sum(row["quantity"] for row in normalized)
    require(type(quantity) is int and 1 <= quantity <= 100000, "quantity_limit", "单次订单开卡量为1～10万张，可分批继续", 400)
    now = timezone.now()
    order = SalesOrder.objects.create(
        organization=actor.organization, responsible=responsible, product=product, source_brand=source,
        mode=mode, entry=entry, quantity=quantity, unit_price_cents=unit_price_cents,
        total_cents=quantity * unit_price_cents, validity_days=product.validity_days,
        units_per_card=units_per_card, product_snapshot=product_snapshot(product), source_name=source.name,
        status="pending_payment" if unit_price_cents else "pending_approval", submitted_at=now, import_batch=batch,
    )
    SalesRow.objects.bulk_create([SalesRow(order=order, row_number=number, raw=raw, normalized=data, quantity=data["quantity"]) for number, raw, data in zip(row_numbers, raw_rows, normalized, strict=True)])
    if batch:
        link_files([str(batch.asset_id)], order)
    audit(actor, order, "sales.submitted", mode=mode, quantity=quantity, total_cents=order.total_cents)
    return order


@transaction.atomic
def submit_receipt(actor, order_id, *, amount_cents, paid_at, payer, reference, attachment_ids, version):
    order = get_order(actor, order_id, lock=True)
    require(not actor.platform, "forbidden", "采购凭证由资源方提交，平台审核", 403)
    check_version(order, version)
    require(order.status == "pending_payment", "invalid_state", "订单当前不接受付款凭证")
    require(type(amount_cents) is int and amount_cents > 0 and amount_cents <= order.total_cents - order.received_cents, "invalid_amount", "金额须为正且不超过剩余采购款", 400)
    require(isinstance(paid_at, datetime) and timezone.is_aware(paid_at) and paid_at <= timezone.now(), "invalid_paid_at", "请填写实际付款时间", 400)
    require(isinstance(payer, str) and payer.strip() and isinstance(reference, str) and reference.strip(), "receipt_required", "请填写付款方及交易参考号", 400)
    assets = validate_attachment_ids(actor, attachment_ids, purposes={"payment"})
    receipt = PurchaseReceipt.objects.create(order=order, amount_cents=amount_cents, paid_at=paid_at, payer=payer.strip(), reference=reference.strip(), reference_index=digest(reference.strip(), purpose="bank_reference"), attachment_ids=[str(a.id) for a in assets], submitted_by=actor.membership)
    link_files(receipt.attachment_ids, order)
    order.status = "payment_review"
    advance(order, "status")
    audit(actor, order, "sales.receipt_submitted", receipt_id=str(receipt.id), amount_cents=amount_cents)
    return receipt


@transaction.atomic
def review_receipt(actor, receipt_id, *, approved, version, reason):
    actor.require_platform()
    ref = PurchaseReceipt.objects.filter(pk=receipt_id).first()
    require(ref, "not_found", "付款凭证不存在", 404)
    order = SalesOrder.objects.select_for_update().get(pk=ref.order_id)
    receipt = PurchaseReceipt.objects.select_for_update().get(pk=receipt_id)
    check_version(receipt, version)
    require(receipt.status == "pending" and order.status == "payment_review", "invalid_state", "付款凭证已处理或订单状态变化")
    require(type(approved) is bool and reason.strip(), "reason_required", "请填写到账核对意见", 400)
    if approved:
        validate_attachment_ids(actor, receipt.attachment_ids, purposes={"payment"})
        advisory_lock("bank_reference", receipt.reference_index)
        require(not PurchaseReceipt.objects.filter(reference_index=receipt.reference_index, status="approved").exists(), "duplicate_receipt", "该采购款流水已确认，不可重复入账")
        order.received_cents += receipt.amount_cents
    receipt.status, receipt.reason = ("approved" if approved else "rejected"), reason
    receipt.reviewed_by, receipt.reviewed_at = actor.membership, timezone.now()
    advance(receipt, "status", "reason", "reviewed_by", "reviewed_at")
    order.status = "pending_approval" if order.received_cents == order.total_cents else "pending_payment"
    advance(order, "received_cents", "status")
    audit(actor, order, "sales.receipt_reviewed", reason=reason, receipt_id=str(receipt.id), status=receipt.status, received_cents=order.received_cents)
    return receipt


@transaction.atomic
def approve_order(actor, order_id, *, approved, version, reason, validity_days=None):
    actor.require_platform()
    order = get_order(actor, order_id, lock=True)
    if order.status == "issued" and approved:
        return order
    check_version(order, version)
    require(order.status == "pending_approval", "invalid_state", "请先确认采购款全额到账，再审核开卡")
    require(type(approved) is bool and reason.strip(), "reason_required", "请填写审核意见", 400)
    if not approved:
        order.status, order.reason, order.reviewed_by = "rejected", reason, actor.membership
        if order.received_cents:
            order.refund = {"status": "pending", "amount_cents": order.received_cents}
        advance(order, "status", "reason", "reviewed_by", "refund")
        audit(actor, order, "sales.rejected", reason=reason)
        return order
    validate_authorization(order)
    require(order.received_cents == order.total_cents, "payment_required", "采购款未全额到账")
    days = order.validity_days if validity_days is None else validity_days
    require(type(days) is int and 1 <= days <= 36500, "invalid_validity", "有效期须为1～36500天", 400)
    rows = list(order.rows.order_by("row_number"))
    if order.mode == "named":
        validate_rows([row.normalized for row in rows])
        # Stable phone lock order avoids deadlocks between overlapping multi-source batches.
        for index in sorted({digest(row.normalized["phone"], purpose="phone") for row in rows}):
            advisory_lock("customer", index)
        for row in rows:
            row.customer = resolve_customer(row.normalized, order_id=order.id)
            row.save(update_fields=["customer"])
    advisory_lock("sequence", "cards")
    sequence, _ = CardSequence.objects.get_or_create(name="cards")
    first = sequence.next_number
    sequence.next_number += order.quantity
    sequence.save(update_fields=["next_number"])
    CardRange.objects.create(order=order, first_number=first, last_number=first + order.quantity - 1)
    order.validity_days = days
    serial = first
    allocations = [(row, row.quantity) for row in rows] if rows else [(None, order.quantity)]
    now = timezone.now()
    for row, count in allocations:
        source = None
        if row:
            source, _ = CustomerSource.objects.get_or_create(customer=row.customer, organization=order.organization)
        # Inserts are bounded per chunk; entire approval remains atomic, including all customer matches.
        for offset in range(0, count, 1000):
            cards = []
            for _ in range(min(1000, count - offset)):
                credential, hashed = new_credential()
                cards.append(Card(order=order, row=row, serial=serial, credential=credential, credential_digest=hashed, customer=row.customer if row else None))
                serial += 1
            Card.objects.bulk_create(cards)
            if row:
                Benefit.objects.bulk_create([Benefit(card=card, customer=row.customer, source=source, product=order.product, total=order.units_per_card, pending=order.units_per_card) for card in cards])
            from chihuitong.models import DomainEvent
            DomainEvent.objects.bulk_create([DomainEvent(card=card, kind="issued", object_id=card.id, occurred_at=now, payload={"customer_id": str(row.customer_id) if row else None}) for card in cards])
    order.status, order.approved_at, order.reason, order.reviewed_by = "issued", now, reason, actor.membership
    advance(order, "status", "approved_at", "reason", "reviewed_by", "validity_days")
    audit(actor, order, "sales.issued", reason=reason, quantity=order.quantity, validity_days=days, first_number=str(first), last_number=str(serial - 1))
    return order


@transaction.atomic
def request_stop(actor, order_id, *, action, version, reason):
    order = get_order(actor, order_id, lock=True)
    require(not actor.platform, "forbidden", "由资源方申请，平台审核", 403)
    check_version(order, version)
    require(action in {"cancel", "stop"} and reason.strip(), "invalid_action", "请选择取消或停止并填写原因", 400)
    require(order.status in {"issued", "pending_payment", "pending_approval"}, "invalid_state", "当前存在未决收款或处理流程，请先核对")
    if action == "stop":
        require(order.mode == "named" and order.status == "issued", "invalid_stop", "只有已开卡记名销售可停止剩余")
    else:
        require(not order.cards.filter(activated_at__isnull=False).exists(), "already_activated", "已有卡片领取或激活，不能整单取消")
    order.previous_status, order.status, order.reason = order.status, action + "_pending", reason
    advance(order, "previous_status", "status", "reason")
    audit(actor, order, "sales.stop_requested", reason=reason, action_kind=action)
    return order


@transaction.atomic
def review_stop(actor, order_id, *, approved, version, reason):
    actor.require_platform()
    order = get_order(actor, order_id, lock=True)
    check_version(order, version)
    require(order.status in {"cancel_pending", "stop_pending"}, "invalid_state", "订单没有待审核的取消或停止申请")
    require(type(approved) is bool and reason.strip(), "reason_required", "请填写审核结论", 400)
    action = order.status
    if not approved:
        order.status = order.previous_status
    else:
        if action == "cancel_pending":
            require(not order.cards.filter(activated_at__isnull=False).exists(), "already_activated", "已有领取或激活，不允许取消")
        cards = order.cards.select_for_update().filter(activated_at__isnull=True, voided_at__isnull=True)
        now = timezone.now()
        for card in cards:
            card.status, card.voided_at = "void", now
            advance(card, "status", "voided_at")
            benefit = Benefit.objects.select_for_update().filter(card=card).first()
            if benefit:
                benefit.pending, benefit.voided = 0, benefit.total
                advance(benefit, "pending", "voided")
            event(card, "voided", at=now, reason=action)
        order.status = "cancelled" if action == "cancel_pending" else "stopped"
        if order.status == "cancelled" and order.received_cents:
            order.refund = {"status": "pending", "amount_cents": order.received_cents}
    order.reason = reason
    advance(order, "status", "reason", "refund")
    audit(actor, order, "sales.stop_reviewed", reason=reason, status=order.status)
    return order


@transaction.atomic
def freeze_card(actor, card_id, *, frozen, reason):
    actor.require_platform()
    ref = Card.objects.filter(pk=card_id).first()
    require(ref, "not_found", "卡片不存在", 404)
    SalesOrder.objects.select_for_update().get(pk=ref.order_id)
    card = Card.objects.select_for_update().get(pk=card_id)
    require(type(frozen) is bool and reason.strip(), "reason_required", "请填写冻结或解冻原因", 400)
    card.frozen = frozen
    advance(card, "frozen")
    audit(actor, card, "card.frozen" if frozen else "card.unfrozen", reason=reason)
    return card


@transaction.atomic
def register_refund(actor, order_id, *, amount_cents, refunded_at, reference, attachment_ids, version, reason):
    actor.require_platform()
    order = get_order(actor, order_id, lock=True)
    check_version(order, version)
    require(order.status in {"cancelled", "rejected"} and order.refund.get("status") == "pending", "invalid_refund", "订单不存在待登记退款")
    require(type(amount_cents) is int and amount_cents == order.received_cents and amount_cents > 0, "invalid_amount", "请登记全额实际退款金额", 400)
    require(isinstance(refunded_at, datetime) and timezone.is_aware(refunded_at) and refunded_at <= timezone.now() and reference.strip() and reason.strip(), "invalid_refund", "请填写实际退款日期、流水及原因", 400)
    validate_attachment_ids(actor, attachment_ids, purposes={"payment"})
    link_files(attachment_ids, order)
    order.refund = {"status": "recorded", "amount_cents": amount_cents, "refunded_at": refunded_at.isoformat(), "reference": reference, "attachment_ids": attachment_ids, "recorded_by": str(actor.membership.id)}
    advance(order, "refund")
    audit(actor, order, "sales.refund_recorded", reason=reason, amount_cents=amount_cents)
    return order


@transaction.atomic
def register_shipment(actor, order_id, *, recipient, phone, address, carrier, tracking_number, version):
    actor.require_platform()
    order = get_order(actor, order_id, lock=True)
    check_version(order, version)
    require(order.mode == "physical" and order.status == "issued", "invalid_shipment", "仅已开卡实体订单可登记寄送")
    from chihuitong.crypto import normalize_phone
    require(all(isinstance(value, str) and value.strip() and len(value) <= 500 for value in [recipient, address, carrier, tracking_number]), "invalid_shipment", "请填写完整寄送资料", 400)
    order.shipment = {"recipient": recipient, "phone": normalize_phone(phone), "address": address, "carrier": carrier, "tracking_number": tracking_number, "shipped_at": timezone.now().isoformat()}
    advance(order, "shipment")
    audit(actor, order, "sales.shipped")
    return order
