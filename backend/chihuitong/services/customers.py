from datetime import timedelta
import secrets
import unicodedata

from django.db import transaction
from django.utils import timezone

from chihuitong.crypto import digest, normalize_phone
from chihuitong.errors import BusinessError, require
from chihuitong.models import Benefit, Card, Customer, CustomerSource, DomainEvent, SalesOrder

from .common import advance, advisory_lock


def normalize_customer(raw):
    require(isinstance(raw, dict) and not(set(raw) - {"name", "phone", "quantity", "resource_customer_no", "gender", "age", "occupation"}), "invalid_customer", "客户字段不合法", 400)
    name = raw.get("name")
    require(isinstance(name, str) and 0 < len(name.strip()) <= 100, "invalid_name", "请填写客户姓名", 400)
    phone = normalize_phone(raw.get("phone"))
    quantity = raw.get("quantity")
    if isinstance(quantity, str) and quantity.isdigit():
        quantity = int(quantity)
    require(type(quantity) is int and 1 <= quantity <= 100000, "invalid_quantity", "开卡数量必须为正整数，单行不超过10万，可分批继续", 400)
    result = {"name": name.strip(), "phone": phone, "quantity": quantity, "resource_customer_no": str(raw.get("resource_customer_no") or "")[:160]}
    gender = raw.get("gender")
    if gender not in {None, ""}:
        gender = unicodedata.normalize("NFKC", str(gender)).strip().lower()
        mapping = {"男": "male", "male": "male", "m": "male", "女": "female", "female": "female", "f": "female", "未知": "unknown", "unknown": "unknown"}
        require(gender in mapping, "invalid_gender", "性别无法识别，请修正或不导入该列", 400)
        result["gender"] = mapping[gender]
    age = raw.get("age")
    if age is not None and age != "":
        if isinstance(age, str) and age.isdigit():
            age = int(age)
        require(type(age) is int and 0 <= age <= 150, "invalid_age", "年龄须为0～150整数，请修正或不导入该列", 400)
        result["age"] = age
    occupation = raw.get("occupation")
    if occupation is not None and occupation != "":
        require(isinstance(occupation, str) and len(occupation.strip()) <= 100, "invalid_occupation", "职业文本过长，请修正或不导入该列", 400)
        result["occupation"] = occupation.strip()
    return result


def match_preview(data):
    existing = Customer.objects.filter(phone_index=digest(data["phone"], purpose="phone")).first()
    require(not existing or existing.name == data["name"], "customer_conflict", "手机号与姓名不一致，请核对当前上传资料", 400)
    return existing


def resolve_customer(data, *, order_id):
    index = digest(data["phone"], purpose="phone")
    advisory_lock("customer", index)
    customer = Customer.objects.select_for_update().filter(phone_index=index).first()
    require(not customer or customer.name == data["name"], "customer_conflict", "手机号与姓名不一致，请核对当前上传资料", 400)
    if not customer:
        customer = Customer.objects.create(phone=data["phone"], phone_index=index, name=data["name"])
    profile = dict(customer.profile)
    sources = dict(profile.get("field_sources", {}))
    for field in ["gender", "age", "occupation"]:
        if profile.get(field) in (None, "") and field in data:
            profile[field] = data[field]
            sources[field] = {"order_id": str(order_id), "captured_at": timezone.now().isoformat()}
    profile["field_sources"] = sources
    customer.profile = profile
    advance(customer, "profile")
    return customer


def event(card, kind, *, obj=None, at=None, **payload):
    return DomainEvent.objects.create(card=card, kind=kind, object_id=obj.id if obj else card.id, occurred_at=at or timezone.now(), payload=payload)


@transaction.atomic
def register_verified_customer(phone, *, name=None):
    """Internal adapter boundary only: caller must have independently verified phone ownership."""
    phone = normalize_phone(phone)
    index = digest(phone, purpose="phone")
    advisory_lock("customer", index)
    customer = Customer.objects.select_for_update().filter(phone_index=index).first()
    if not customer:
        require(isinstance(name, str) and name.strip(), "name_required", "请填写客户姓名", 400)
        customer = Customer.objects.create(phone=phone, phone_index=index, name=name.strip())
    if customer.registered_at is None:
        customer.registered_at = timezone.now()
        advance(customer, "registered_at")
    return customer


@transaction.atomic
def claim(customer_id, card_id):
    # Global lock ordering: order -> card -> customer -> benefit. Cancel/stop follows the same order.
    card_ref = Card.objects.filter(pk=card_id).first()
    require(card_ref, "not_found", "权益不存在", 404)
    order = SalesOrder.objects.select_for_update().get(pk=card_ref.order_id)
    card = Card.objects.select_for_update().get(pk=card_id)
    customer = Customer.objects.select_for_update().filter(pk=customer_id, registered_at__isnull=False).first()
    require(customer and card.customer_id == customer.id, "not_found", "权益不存在或不属于当前客户", 404)
    require(order.mode == "named", "invalid_claim", "实体卡请扫码激活")
    if card.activated_at:
        return Benefit.objects.get(card=card)
    require(order.status == "issued" and card.status == "unclaimed" and not card.frozen, "claim_unavailable", "当前权益暂不可领取")
    benefit = Benefit.objects.select_for_update().get(card=card)
    now = timezone.now()
    benefit.pending, benefit.available = 0, benefit.total
    benefit.activated_at, benefit.expires_at = now, now + timedelta(days=order.validity_days)
    advance(benefit, "pending", "available", "activated_at", "expires_at")
    card.activated_at, card.status = now, "active"
    advance(card, "activated_at", "status")
    event(card, "activated", at=now, customer_id=str(customer.id))
    return benefit


@transaction.atomic
def activate(customer_id, credential):
    require(isinstance(credential, str) and 20 <= len(credential) <= 200, "invalid_card", "卡片凭证不合法", 400)
    ref = Card.objects.filter(credential_digest=digest(credential, purpose="card")).first()
    require(ref, "not_found", "卡片无效，请核对卡面二维码", 404)
    order = SalesOrder.objects.select_for_update().get(pk=ref.order_id)
    card = Card.objects.select_for_update().get(pk=ref.pk)
    customer = Customer.objects.select_for_update().filter(pk=customer_id, registered_at__isnull=False).first()
    require(customer, "customer_unbound", "请先授权手机号登录", 403)
    require(order.mode == "physical", "invalid_card", "此卡片请通过待领取权益领取")
    if card.activated_at:
        require(card.customer_id == customer.id, "already_activated", "卡片已激活，不支持转让")
        return Benefit.objects.get(card=card)
    require(order.status == "issued" and card.status == "unclaimed" and not card.frozen, "activation_unavailable", "卡片当前不可激活")
    source, _ = CustomerSource.objects.get_or_create(customer=customer, organization=order.organization)
    now = timezone.now()
    benefit = Benefit.objects.create(card=card, customer=customer, source=source, product=order.product, total=order.units_per_card, available=order.units_per_card, activated_at=now, expires_at=now + timedelta(days=order.validity_days))
    card.customer, card.activated_at, card.status = customer, now, "active"
    advance(card, "customer", "activated_at", "status")
    event(card, "activated", at=now, customer_id=str(customer.id))
    return benefit


@transaction.atomic
def update_profile(customer_id, data):
    require(isinstance(data, dict) and not (set(data) - {"name", "gender", "age", "occupation"}), "invalid_fields", "仅可修改姓名、性别、年龄和职业，不可修改手机号", 400)
    customer = Customer.objects.select_for_update().filter(pk=customer_id, registered_at__isnull=False).first()
    require(customer, "not_found", "客户不存在", 404)
    normalized = normalize_customer({"name": data.get("name", customer.name), "phone": customer.phone, "quantity": 1, **data})
    profile = dict(customer.profile)
    for key in ["gender", "age", "occupation"]:
        if key in data:
            profile[key] = normalized.get(key)
            profile.setdefault("field_sources", {})[key] = {"source": "customer", "captured_at": timezone.now().isoformat()}
    customer.name, customer.profile = normalized["name"], profile
    advance(customer, "name", "profile")
    return customer


def new_credential():
    token = secrets.token_urlsafe(32)
    return token, digest(token, purpose="card")
