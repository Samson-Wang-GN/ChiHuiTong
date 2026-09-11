"""Customer-visible clinic projection. Selection mirrors new-booking authorization in SQL."""
from django.db.models import Exists, FloatField, OuterRef, Subquery
from django.db.models.expressions import RawSQL
from django.utils import timezone

from chihuitong.errors import require
from chihuitong.models import Appointment, Benefit, Clinic, ContractProduct, ContractVersion


def eligible_clinics(product_id):
    now = timezone.now()
    versions = ContractVersion.objects.filter(
        status__in=["approved", "terminated"], starts_at__lte=now, reviewed_at__lte=now
    ).order_by("-starts_at", "-revision")
    clinic_versions = versions.filter(
        contract__organization_id=OuterRef("organization_id"), channel_id=OuterRef("channel_id")
    )
    channel_versions = versions.filter(contract__organization_id=OuterRef("channel_id"))
    qs = Clinic.objects.select_related("organization").filter(
        organization__status="active", channel__status="active", service_status="online",
        review_status="approved", profile_version__gt=0,
        products__product_id=product_id, products__status="online", products__product__status="active",
    ).annotate(
        clinic_contract=Subquery(clinic_versions.values("id")[:1]),
        channel_contract=Subquery(channel_versions.values("id")[:1]),
    )
    # Select the latest version BEFORE testing its validity; never fall back to a superseded one.
    valid = ContractVersion.objects.filter(status="approved", ends_at__gte=now)
    return qs.filter(
        clinic_contract__in=valid.values("id"), channel_contract__in=valid.values("id")
    ).annotate(authorized=Exists(ContractProduct.objects.filter(
        contract_version_id=OuterRef("channel_contract"), product_id=product_id, status="active"
    ))).filter(authorized=True)


def owned_benefit(customer, benefit_id, *, bookable=True):
    benefit = Benefit.objects.select_related("card__order").filter(pk=benefit_id, customer=customer).first()
    require(benefit, "not_found", "权益不存在", 404)
    if bookable:
        require(
            benefit.card.status == "active" and not benefit.card.frozen and benefit.activated_at
            and benefit.expires_at and timezone.localtime(benefit.expires_at).date() >= timezone.localdate()
            and benefit.available >= benefit.card.order.product_snapshot["redemption_units"],
            "benefit_unavailable", "请使用有效且有可预约份数的权益查询门诊",
        )
    return benefit


def listing(customer, benefit_id, *, longitude=None, latitude=None, query=""):
    benefit = owned_benefit(customer, benefit_id)
    qs = eligible_clinics(benefit.product_id)
    if query:
        qs = qs.filter(organization__name__icontains=query)
    if longitude is not None:
        # Bound parameters only; no external map call and no customer location persistence.
        distance = RawSQL(
            'CASE WHEN "chihuitong_clinic"."latitude" IS NULL OR "chihuitong_clinic"."longitude" IS NULL THEN NULL ELSE '
            '6371000 * 2 * asin(sqrt(least(1.0, greatest(0.0, '
            'power(sin(radians("chihuitong_clinic"."latitude"::float8 - %s) / 2), 2) + '
            'cos(radians(%s)) * cos(radians("chihuitong_clinic"."latitude"::float8)) * '
            'power(sin(radians("chihuitong_clinic"."longitude"::float8 - %s) / 2), 2))))) END',
            (float(latitude), float(latitude), float(longitude)), output_field=FloatField(),
        )
        qs = qs.annotate(distance_m=distance).order_by("distance_m", "id")
    else:
        qs = qs.order_by("organization__name", "id")
    return qs


def detail(customer, clinic_id, *, benefit_id=None):
    own = Appointment.objects.filter(customer=customer, clinic_id=clinic_id).exists()
    if own:
        clinic = Clinic.objects.select_related("organization").filter(pk=clinic_id).first()
    else:
        require(benefit_id, "benefit_required", "请先选择本人权益", 400)
        benefit = owned_benefit(customer, benefit_id)
        clinic = eligible_clinics(benefit.product_id).filter(pk=clinic_id).first()
    require(clinic, "not_found", "门诊不存在或暂不可预约", 404)
    return clinic


def projection(clinic):
    data = clinic.profile
    return {
        "id": str(clinic.id), "name": clinic.organization.name,
        **{key: data.get(key) for key in ["province", "city", "district", "address", "business_hours", "frontdesk_phone"]},
        "cover_available": bool(data.get("cover_id")),
        "longitude": clinic.longitude, "latitude": clinic.latitude, "coordinate_system": "GCJ-02",
        "distance_m": round(clinic.distance_m) if getattr(clinic, "distance_m", None) is not None else None,
        "distance_kind": "straight_line", "service_status": clinic.service_status,
    }
