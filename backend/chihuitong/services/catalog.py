from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.db import transaction

from chihuitong.errors import BusinessError, require
from chihuitong.models import Organization, Product, ProductRevision, SourceBrand

from .common import RESOURCE_KINDS, advance, audit, check_version


def cents(value):
    try:
        require(
            not isinstance(value, (float, bool)), "invalid_money", "金额必须为十进制字符串", 400
        )
        amount = Decimal(str(value))
        require(
            amount.is_finite() and 0 <= amount <= Decimal("9999999999.99"),
            "invalid_money",
            "金额超出有效范围",
            400,
        )
        return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise BusinessError("invalid_money", "金额格式不正确", 400) from exc


def product_snapshot(product):
    return {
        "id": str(product.id),
        "version": product.version,
        "internal_name": product.internal_name,
        "external_name": product.external_name,
        "status": product.status,
        "product_type": product.product_type,
        "usage_rules": product.usage_rules,
        "redemption_units": product.redemption_units,
        "fee_cents": product.fee_cents,
        "validity_days": product.validity_days,
    }


def validate_product(data):
    allowed = {
        "internal_name",
        "external_name",
        "product_type",
        "usage_rules",
        "redemption_units",
        "fee_cents",
        "validity_days",
        "status",
    }
    require(set(data) == allowed, "invalid_fields", "请填写完整的推广产品字段", 400)
    for key in ["internal_name", "external_name", "usage_rules"]:
        limit = 160 if key.endswith("name") else 10000
        require(
            isinstance(data[key], str) and 0 < len(data[key].strip()) <= limit,
            "invalid_product",
            "产品名称及使用规则不能为空或超长",
            400,
        )
    require(data["status"] in {"active", "disabled"}, "invalid_status", "产品状态不合法", 400)
    require(
        data["product_type"] in {"service", "deduction", "discount"},
        "invalid_type",
        "产品类型不合法",
        400,
    )
    for key in ["redemption_units", "validity_days", "fee_cents"]:
        minimum = 0 if key == "fee_cents" else 1
        require(
            type(data[key]) is int and minimum <= data[key] <= 1000000000,
            "invalid_quantity",
            "数量、天数或费用不合法",
            400,
        )


@transaction.atomic
def save_product(actor, data, *, product_id=None, version=None, reason=""):
    actor.require_platform()
    validate_product(data)
    if product_id:
        product = Product.objects.select_for_update().filter(pk=product_id).first()
        require(product, "not_found", "产品不存在", 404)
        check_version(product, version)
        require(reason.strip(), "reason_required", "请填写产品变更原因", 400)
        for key, value in data.items():
            setattr(product, key, value)
        from .contracts import validate_allocations

        validate_allocations(product)
        advance(product, *data)
    else:
        product = Product.objects.create(**data)
    ProductRevision.objects.create(
        product=product, revision=product.version, snapshot=product_snapshot(product)
    )
    audit(actor, product, "product.saved", reason=reason, version=product.version)
    return product


@transaction.atomic
def save_brand(actor, org_id, *, name, status="active", brand_id=None, version=None):
    actor.require_platform()
    org = Organization.objects.filter(pk=org_id, kind__in=RESOURCE_KINDS).first()
    require(org, "not_found", "客户资源方不存在", 404)
    require(
        isinstance(name, str) and 0 < len(name.strip()) <= 160 and status in {"active", "disabled"},
        "invalid_brand",
        "来源名称或状态不合法",
        400,
    )
    if brand_id:
        brand = (
            SourceBrand.objects.select_for_update().filter(pk=brand_id, organization=org).first()
        )
        require(brand, "not_found", "来源配置不存在", 404)
        check_version(brand, version)
        brand.name, brand.status = name.strip(), status
        advance(brand, "name", "status")
    else:
        brand = SourceBrand.objects.create(organization=org, name=name.strip(), status=status)
    audit(actor, brand, "source_brand.saved", version=brand.version, status=brand.status)
    return brand
