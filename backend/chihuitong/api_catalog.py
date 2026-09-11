from django.http import HttpResponse
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .api import StrictSerializer, paginated, validated
from .errors import BusinessError, require
from .identity import request_actor
from .models import ClinicProduct, ClinicProfileChange, ContractProduct, ContractVersion, FileAsset, Product, SourceBrand
from .services import catalog, clinics, contracts, files
from .services.common import RESOURCE_KINDS


class ProductInput(StrictSerializer):
    internal_name = serializers.CharField(max_length=160)
    external_name = serializers.CharField(max_length=160)
    product_type = serializers.ChoiceField(choices=["service", "deduction", "discount"])
    usage_rules = serializers.CharField(max_length=10000)
    redemption_units = serializers.IntegerField(min_value=1, max_value=1000000000)
    fee_cents = serializers.IntegerField(min_value=0, max_value=1000000000)
    validity_days = serializers.IntegerField(min_value=1, max_value=36500)
    status = serializers.ChoiceField(choices=["active", "disabled"])


class ProductUpdate(StrictSerializer):
    product = ProductInput()
    version = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=500)


@api_view(["GET", "POST"])
def product_list(request):
    actor = request_actor(request)
    actor.require_platform()
    if request.method == "POST":
        return Response(catalog.product_snapshot(catalog.save_product(actor, validated(ProductInput, request))), status=201)
    qs = Product.objects.all()
    if request.query_params.get("search"):
        qs = qs.filter(internal_name__icontains=request.query_params["search"][:160])
    return paginated(request, qs, catalog.product_snapshot, states=["active", "disabled"])


@api_view(["POST"])
def product_update(request, product_id):
    data = validated(ProductUpdate, request)
    product = catalog.save_product(request_actor(request), data.pop("product"), product_id=product_id, **data)
    return Response(catalog.product_snapshot(product))


class BrandInput(StrictSerializer):
    name = serializers.CharField(max_length=160)
    status = serializers.ChoiceField(choices=["active", "disabled"], default="active")
    brand_id = serializers.UUIDField(required=False)
    version = serializers.IntegerField(required=False, min_value=1)


def brand_projection(brand):
    return {"id": str(brand.id), "organization_id": str(brand.organization_id), "name": brand.name, "status": brand.status, "version": brand.version}


@api_view(["GET", "POST"])
def brand_list(request, org_id):
    actor = request_actor(request)
    if request.method == "POST":
        return Response(brand_projection(catalog.save_brand(actor, org_id, **validated(BrandInput, request))))
    require(actor.platform or (actor.organization.id == org_id and actor.organization.kind in RESOURCE_KINDS), "not_found", "机构不存在或无权访问", 404)
    return paginated(request, SourceBrand.objects.filter(organization_id=org_id), brand_projection, states=["active", "disabled"])


class UploadInput(StrictSerializer):
    file = serializers.FileField(max_length=200)
    purpose = serializers.ChoiceField(choices=sorted(files.PURPOSES))


@api_view(["POST"])
def upload(request):
    actor = request_actor(request)
    data = validated(UploadInput, request)
    file = data["file"]
    asset = files.upload_file(actor, data=file.read(files.MAX_FILE + 1), filename=file.name, purpose=data["purpose"])
    return Response({"id": str(asset.id), "content_type": asset.content_type, "size": asset.size, "status": asset.status}, status=201)


@api_view(["GET"])
def download(request, asset_id):
    asset, data = files.download_file(request_actor(request), asset_id)
    response = HttpResponse(data, content_type=asset.content_type)
    suffix = {"image/jpeg": ".jpg", "application/pdf": ".pdf"}.get(asset.content_type, ".xlsx")
    response["Content-Disposition"] = f'attachment; filename="attachment-{asset.id}{suffix}"'
    response["Content-Security-Policy"] = "sandbox; default-src 'none'"
    return response


class ContractData(StrictSerializer):
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    settlement_cycle = serializers.ChoiceField(choices=["monthly", "weekly"])
    contact = serializers.JSONField()
    attachment_ids = serializers.ListField(child=serializers.CharField(max_length=36), min_length=1, max_length=20)


class ContractInput(StrictSerializer):
    number = serializers.CharField(max_length=80)
    data = ContractData()


class VersionInput(StrictSerializer):
    version = serializers.IntegerField(min_value=1)


class ReviewInput(VersionInput):
    approved = serializers.BooleanField()
    reason = serializers.CharField(max_length=500)


class TermInput(StrictSerializer):
    product_id = serializers.UUIDField()
    mode = serializers.ChoiceField(choices=["percent", "amount"])
    value = serializers.CharField(max_length=30)
    status = serializers.ChoiceField(choices=["active", "disabled"])
    version = serializers.IntegerField(min_value=1, required=False)
    reason = serializers.CharField(max_length=500)


def contract_projection(item):
    return {"id": str(item.id), "contract_id": str(item.contract_id), "organization_id": str(item.contract.organization_id), "number": item.contract.number, "kind": item.contract.kind, "revision": item.revision, "version": item.version, "status": item.status, "starts_at": item.starts_at.isoformat(), "ends_at": item.ends_at.isoformat(), "settlement_cycle": item.settlement_cycle, "channel_id": str(item.channel_id) if item.channel_id else None, "contact": item.contact, "attachment_ids": item.attachment_ids, "reason": item.reason}


@api_view(["GET", "POST"])
def contract_list(request, org_id):
    actor = request_actor(request)
    if request.method == "POST":
        return Response(contract_projection(contracts.create_version(actor, org_id, **validated(ContractInput, request))), status=201)
    if not actor.platform:
        # Empty contract is allowed only for an institution itself or its managed clinic.
        owned = actor.organization.id == org_id
        managed = clinics.visible_clinics(actor).filter(organization_id=org_id).exists()
        require(owned or managed, "not_found", "机构不存在或无权访问", 404)
    qs = ContractVersion.objects.select_related("contract").filter(contract__in=contracts.accessible_contracts(actor), contract__organization_id=org_id)
    return paginated(request, qs, contract_projection, states=["draft", "pending", "approved", "rejected", "terminated"])


@api_view(["POST"])
def contract_submit(request, version_id):
    item = contracts.submit_version(request_actor(request), version_id, **validated(VersionInput, request))
    return Response(contract_projection(item))


@api_view(["POST"])
def contract_review(request, version_id):
    item = contracts.review_version(request_actor(request), version_id, **validated(ReviewInput, request))
    return Response(contract_projection(item))


@api_view(["GET", "POST"])
def contract_products(request, version_id):
    actor = request_actor(request)
    if request.method == "POST":
        term = contracts.save_term(actor, version_id, **validated(TermInput, request))
        return Response(contracts.term_snapshot(term))
    item = ContractVersion.objects.filter(pk=version_id, contract__in=contracts.accessible_contracts(actor)).first()
    require(item, "not_found", "合同不存在或无权访问", 404)
    qs = ContractProduct.objects.select_related("product").filter(contract_version=item)
    return paginated(request, qs, lambda t: {**contracts.term_snapshot(t), "product": catalog.product_snapshot(t.product)}, states=["active", "disabled"])


class ClinicInput(StrictSerializer):
    channel_id = serializers.UUIDField()
    profile = serializers.JSONField()
    admin_name = serializers.CharField(max_length=100)
    admin_phone = serializers.CharField(max_length=40)


class ProfileInput(VersionInput):
    profile = serializers.JSONField()


class ServiceInput(VersionInput):
    status = serializers.ChoiceField(choices=["online", "offline", "paused", "exited"])
    reason = serializers.CharField(max_length=500)


class HoursInput(VersionInput):
    hours = serializers.IntegerField(min_value=1, max_value=168)
    reason = serializers.CharField(max_length=500)


class ClinicProductInput(StrictSerializer):
    product_id = serializers.UUIDField()
    online = serializers.BooleanField()
    reason = serializers.CharField(max_length=500)


class ChannelInput(VersionInput):
    channel_id = serializers.UUIDField()
    responsible_id = serializers.UUIDField()
    reason = serializers.CharField(max_length=500)


def clinic_projection(clinic):
    return {"id": str(clinic.id), "organization_id": str(clinic.organization_id), "channel_id": str(clinic.channel_id), "responsible_id": str(clinic.responsible_id), "profile": clinic.profile, "profile_version": clinic.profile_version, "version": clinic.version, "review_status": clinic.review_status, "service_status": clinic.service_status, "confirmation_hours": clinic.confirmation_hours}


def change_projection(change):
    return {"id": str(change.id), "clinic_id": str(change.clinic_id), "base_version": change.base_version, "before": change.before, "after": change.after, "status": change.status, "reason": change.reason, "due_at": change.due_at.isoformat(), "version": change.version}


@api_view(["GET", "POST"])
def clinic_list(request):
    actor = request_actor(request)
    if actor.organization.kind == "clinic":
        actor.require_admin()
    if request.method == "POST":
        return Response(clinic_projection(clinics.create_clinic(actor, **validated(ClinicInput, request))), status=201)
    qs = clinics.visible_clinics(actor)
    if request.query_params.get("search"):
        qs = qs.filter(organization__name__icontains=request.query_params["search"][:200])
    return paginated(request, qs, clinic_projection, status_field="service_status", states=["online", "offline", "paused", "exited"])


@api_view(["GET"])
def clinic_detail(request, clinic_id):
    actor = request_actor(request)
    if actor.organization.kind == "clinic":
        actor.require_admin()
    return Response(clinic_projection(clinics.get_clinic(actor, clinic_id)))


@api_view(["GET", "POST"])
def profile_changes(request, clinic_id):
    actor = request_actor(request)
    if actor.organization.kind == "clinic":
        actor.require_admin()
    clinic = clinics.get_clinic(actor, clinic_id, edit=request.method == "POST")
    if request.method == "POST":
        return Response(change_projection(clinics.submit_profile(actor, clinic_id, **validated(ProfileInput, request))), status=201)
    return paginated(request, ClinicProfileChange.objects.filter(clinic=clinic), change_projection, states=["pending", "approved", "rejected"])


@api_view(["POST"])
def profile_review(request, change_id):
    return Response(change_projection(clinics.review_profile(request_actor(request), change_id, **validated(ReviewInput, request))))


@api_view(["POST"])
def clinic_service(request, clinic_id):
    return Response(clinic_projection(clinics.set_service_status(request_actor(request), clinic_id, **validated(ServiceInput, request))))


@api_view(["POST"])
def clinic_hours(request, clinic_id):
    return Response(clinic_projection(clinics.set_confirmation_hours(request_actor(request), clinic_id, **validated(HoursInput, request))))


@api_view(["POST"])
def clinic_channel(request, clinic_id):
    return Response(clinic_projection(clinics.change_channel(request_actor(request), clinic_id, **validated(ChannelInput, request))))


@api_view(["GET", "POST"])
def clinic_products(request, clinic_id):
    actor = request_actor(request)
    clinic = clinics.get_clinic(actor, clinic_id)
    if request.method == "POST":
        link = clinics.set_clinic_product(actor, clinic_id, **validated(ClinicProductInput, request))
        return Response({"id": str(link.id), "product_id": str(link.product_id), "status": link.status, "version": link.version})
    try:
        current = contracts.current_contract(clinic.channel_id)
    except BusinessError as exc:
        return Response({"results": [], "reason": exc.message, "total": 0, "counts": {"all": 0, "online": 0, "offline": 0}})
    qs = Product.objects.filter(contractproduct__contract_version=current, contractproduct__status="active")
    links = {str(p.product_id): p.status for p in ClinicProduct.objects.filter(clinic=clinic)}
    # Products not explicitly configured are offline; default display is all channel-authorized products.
    from django.db.models import Case, CharField, Value, When
    online_ids = [key for key, value in links.items() if value == "online"]
    qs = qs.annotate(clinic_state=Case(When(id__in=online_ids, then=Value("online")), default=Value("offline"), output_field=CharField()))
    return paginated(request, qs, lambda p: {"product_id": str(p.id), "internal_name": p.internal_name, "external_name": p.external_name, "usage_rules": p.usage_rules, "fee_cents": p.fee_cents, "status": p.clinic_state}, status_field="clinic_state", states=["online", "offline"])
