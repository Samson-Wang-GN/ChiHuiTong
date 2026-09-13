from django.http import HttpResponse
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .api import StrictSerializer, validated
from .errors import require
from .identity import rate_limit, request_actor
from .integrations.tencent_map import geocode, static_map
from .services.clinics import get_clinic
from .services.common import audit


class GeocodeInput(StrictSerializer):
    clinic_id = serializers.UUIDField(required=False)
    province = serializers.CharField(max_length=100)
    city = serializers.CharField(max_length=100)
    district = serializers.CharField(max_length=100)
    address = serializers.CharField(max_length=300)


class MapInput(StrictSerializer):
    clinic_id = serializers.UUIDField(required=False)
    latitude = serializers.DecimalField(
        max_digits=10, decimal_places=6, min_value=-85, max_value=85
    )
    longitude = serializers.DecimalField(
        max_digits=10, decimal_places=6, min_value=-180, max_value=180
    )
    zoom = serializers.IntegerField(min_value=3, max_value=18)


class ProfileMapInput(StrictSerializer):
    change_id = serializers.UUIDField(required=False)
    snapshot = serializers.ChoiceField(choices=["before", "after"], default="after")
    zoom = serializers.IntegerField(min_value=4, max_value=18, default=17)


@api_view(["POST"])
def profile_map(request, clinic_id):
    """Read-only, server-selected saved snapshot; never accepts arbitrary coordinates."""
    actor = request_actor(request)
    if actor.organization.kind == "clinic":
        actor.require_admin()
    clinic = get_clinic(actor, clinic_id)
    data = validated(ProfileMapInput, request)
    profile = clinic.profile
    if data.get("change_id"):
        change = clinic.profile_changes.filter(pk=data["change_id"]).first()
        require(change, "not_found", "资料申请不存在或无权访问", 404)
        profile = getattr(change, data["snapshot"])
    location = profile.get("location") or {}
    require(
        location.get("status") == "confirmed"
        and location.get("latitude") is not None
        and location.get("longitude") is not None,
        "location_unconfirmed",
        "此版本尚无已确认的位置，不能显示准确地图",
        409,
    )
    rate_limit(f"map-preview:{actor.membership.id}", seconds=60, maximum=60)
    response = HttpResponse(
        static_map(location["latitude"], location["longitude"], data["zoom"]),
        content_type="image/png",
    )
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@api_view(["POST"])
def map_preview(request):
    actor = request_actor(request)
    require(
        actor.platform or actor.organization.kind in {"channel", "clinic"},
        "forbidden",
        "仅门诊资料维护人员可处理定位",
        403,
    )
    if actor.organization.kind == "clinic":
        actor.require_admin()
    data = validated(MapInput, request)
    if data.get("clinic_id"):
        get_clinic(actor, data["clinic_id"], edit=True)
    else:
        require(
            actor.platform or actor.organization.kind == "channel",
            "clinic_required",
            "请选择本人门诊",
            400,
        )
    rate_limit(f"map-preview:{actor.membership.id}", seconds=60, maximum=60)
    response = HttpResponse(
        static_map(data["latitude"], data["longitude"], data["zoom"]), content_type="image/png"
    )
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@api_view(["POST"])
def locate(request):
    actor = request_actor(request)
    require(
        actor.platform or actor.organization.kind in {"channel", "clinic"},
        "forbidden",
        "仅门诊资料维护人员可处理定位",
        403,
    )
    if actor.organization.kind == "clinic":
        actor.require_admin()
    data = validated(GeocodeInput, request)
    if data.get("clinic_id"):
        obj = get_clinic(actor, data["clinic_id"], edit=True)
    else:
        require(
            actor.platform or actor.organization.kind == "channel",
            "clinic_required",
            "请选择本人门诊",
            400,
        )
        obj = actor.organization
    rate_limit(f"geocode:{actor.membership.id}", seconds=60, maximum=30)
    address = "".join(data[key] for key in ["province", "city", "district", "address"])
    result = geocode(address)
    audit(
        actor,
        obj,
        "clinic.location_candidate_requested",
        provider="tencent",
        precision=result["precision"],
        requires_confirmation=True,
    )
    return Response(
        {
            "candidate": result,
            "message": "请在地图上核对门诊位置；确认后随门诊资料提交平台审核，不会直接覆盖已生效坐标。",
        }
    )
