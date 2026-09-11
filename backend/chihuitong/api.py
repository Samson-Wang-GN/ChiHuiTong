from django.db import connection
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .identity import request_actor, request_code, verify_code
from .models import Membership, Organization
from .services import organizations


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError({"non_field_errors": ["请求内容必须为对象"]})
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({"fields": "存在不允许修改的字段"})
        return super().to_internal_value(data)


class PhoneInput(StrictSerializer):
    phone = serializers.CharField(max_length=40)


class LoginInput(PhoneInput):
    code = serializers.RegexField(r"^\d{6}$")


def validated(serializer, request):
    form = serializer(data=request.data)
    form.is_valid(raise_exception=True)
    return form.validated_data


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def health(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    return Response({"status": "ok", "service": "chihuitong"})


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def send_code(request):
    return Response(
        request_code(
            validated(PhoneInput, request)["phone"], request.META.get("REMOTE_ADDR", "unknown")
        )
    )


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def login(request):
    return Response(
        verify_code(
            **validated(LoginInput, request),
            remote_address=request.META.get("REMOTE_ADDR", "unknown"),
        )
    )


@api_view(["POST"])
def logout(request):
    request.auth.revoked_at = timezone.now()
    request.auth.save(update_fields=["revoked_at"])
    return Response({"logged_out": True})


@api_view(["GET"])
def me(request):
    memberships = Membership.objects.select_related("organization").filter(
        account=request.user, active=True, organization__status="active"
    )
    return Response(
        {
            "account_id": str(request.user.id),
            "memberships": [
                {
                    "id": str(m.id),
                    "organization_id": str(m.organization_id),
                    "organization_name": m.organization.name,
                    "kind": m.organization.kind,
                    "role": m.role,
                }
                for m in memberships
            ],
        }
    )


class OrganizationInput(StrictSerializer):
    name = serializers.CharField(max_length=200)
    kind = serializers.ChoiceField(choices=["insurance", "bank", "broker", "channel"])
    admin_name = serializers.CharField(max_length=100)
    admin_phone = serializers.CharField(max_length=40)
    contact_name = serializers.CharField(max_length=100, required=False)
    contact_phone = serializers.CharField(max_length=40, required=False)


class MemberInput(StrictSerializer):
    name = serializers.CharField(max_length=100)
    phone = serializers.CharField(max_length=40)
    role = serializers.ChoiceField(choices=["admin", "staff"])


class MemberUpdate(StrictSerializer):
    role = serializers.ChoiceField(choices=["admin", "staff"])
    active = serializers.BooleanField()
    version = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=500)


class OrganizationUpdate(StrictSerializer):
    status = serializers.ChoiceField(choices=["active", "disabled"])
    version = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=500)


def org_projection(org):
    return {
        "id": str(org.id),
        "name": org.name,
        "kind": org.kind,
        "status": org.status,
        "version": org.version,
    }


def paginated(request, queryset, projection, *, status_field="status", states=()):
    """Tab counts use the same already-authorized/filtered query, before state filtering."""
    from django.db.models import Count

    try:
        page = int(request.query_params.get("page", 1))
        size = int(request.query_params.get("page_size", 20))
    except (ValueError, TypeError) as exc:
        raise serializers.ValidationError("分页参数不合法") from exc
    if page < 1 or size < 1 or size > 100:
        raise serializers.ValidationError("分页大小必须为1～100")
    counts = {state: 0 for state in states}
    if status_field:
        counts.update(
            {
                item[status_field]: item["total"]
                for item in queryset.order_by().values(status_field).annotate(total=Count("pk"))
            }
        )
    counts["all"] = queryset.count()
    state = request.query_params.get("status", "all")
    if state != "all":
        if status_field == "active":
            state = {"active": True, "disabled": False}.get(state, state)
        if not status_field or state not in counts:
            raise serializers.ValidationError("列表状态不合法")
        queryset = queryset.filter(**{status_field: state})
    total = queryset.count()
    rows = queryset.order_by("-created_at", "id")[(page - 1) * size : page * size]
    if status_field == "active":
        counts = {
            "active": counts.get(True, 0),
            "disabled": counts.get(False, 0),
            "all": counts["all"],
        }
    return Response(
        {
            "results": [projection(row) for row in rows],
            "total": total,
            "counts": counts,
            "page": page,
            "page_size": size,
        }
    )


@api_view(["GET", "POST"])
def organization_list(request):
    actor = request_actor(request)
    actor.require_platform()
    if request.method == "POST":
        org = organizations.create_organization(actor, **validated(OrganizationInput, request))
        return Response(org_projection(org), status=201)
    qs = Organization.objects.exclude(kind="platform")
    search = request.query_params.get("search", "").strip()
    if search:
        qs = qs.filter(name__icontains=search[:200])
    return paginated(
        request, qs, org_projection, states=["active", "disabled", "pending", "rejected"]
    )


class OrganizationDetailsInput(StrictSerializer):
    name = serializers.CharField(max_length=200)
    contact_name = serializers.CharField(max_length=100)
    contact_phone = serializers.CharField(max_length=40)
    version = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=500)


class OrganizationReviewInput(StrictSerializer):
    approved = serializers.BooleanField()
    version = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=500)


class OrganizationResubmitInput(StrictSerializer):
    version = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=500)


@api_view(["GET", "POST"])
def organization_detail(request, org_id):
    actor = request_actor(request)
    if request.method == "POST":
        org = organizations.update_organization(
            actor, org_id, **validated(OrganizationDetailsInput, request)
        )
    else:
        org = organizations.managed_org(actor, org_id)
    return Response({**org_projection(org), "details": org.details})


@api_view(["POST"])
def organization_review(request, org_id):
    return Response(
        org_projection(
            organizations.review_organization(
                request_actor(request), org_id, **validated(OrganizationReviewInput, request)
            )
        )
    )


@api_view(["POST"])
def organization_resubmit(request, org_id):
    return Response(
        org_projection(
            organizations.resubmit_organization(
                request_actor(request), org_id, **validated(OrganizationResubmitInput, request)
            )
        )
    )


@api_view(["POST"])
def organization_status(request, org_id):
    return Response(
        org_projection(
            organizations.set_organization_status(
                request_actor(request), org_id, **validated(OrganizationUpdate, request)
            )
        )
    )


@api_view(["GET", "POST"])
def member_list(request, org_id):
    actor = request_actor(request)
    org = organizations.managed_org(actor, org_id)
    if request.method == "POST":
        member = organizations.create_member(actor, org.id, **validated(MemberInput, request))
        return Response(organizations.member_projection(member), status=201)
    qs = Membership.objects.select_related("account").filter(organization=org)
    return paginated(
        request, qs, organizations.member_projection, status_field="active", states=[True, False]
    )


@api_view(["POST"])
def member_update(request, member_id):
    member = organizations.update_member(
        request_actor(request), member_id, **validated(MemberUpdate, request)
    )
    return Response(organizations.member_projection(member))
