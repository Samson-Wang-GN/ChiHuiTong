from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .api import StrictSerializer, validated
from .errors import require
from .identity import rate_limit, request_actor
from .integrations.tencent_map import geocode
from .services.clinics import get_clinic
from .services.common import audit


class GeocodeInput(StrictSerializer):
    clinic_id = serializers.UUIDField(required=False)
    province = serializers.CharField(max_length=100)
    city = serializers.CharField(max_length=100)
    district = serializers.CharField(max_length=100)
    address = serializers.CharField(max_length=300)


@api_view(["POST"])
def locate(request):
    actor = request_actor(request)
    require(actor.platform or actor.organization.kind in {"channel", "clinic"}, "forbidden", "仅门诊资料维护人员可处理定位", 403)
    if actor.organization.kind == "clinic":
        actor.require_admin()
    data = validated(GeocodeInput, request)
    if data.get("clinic_id"):
        obj = get_clinic(actor, data["clinic_id"], edit=True)
    else:
        require(actor.platform or actor.organization.kind == "channel", "clinic_required", "请选择本人门诊", 400)
        obj = actor.organization
    rate_limit(f"geocode:{actor.membership.id}", seconds=60, maximum=30)
    address = "".join(data[key] for key in ["province", "city", "district", "address"])
    result = geocode(address)
    audit(actor, obj, "clinic.location_candidate_requested", provider="tencent", precision=result["precision"], requires_confirmation=True)
    return Response({"candidate": result, "message": "请在地图上核对门诊位置；确认后随门诊资料提交平台审核，不会直接覆盖已生效坐标。"})
