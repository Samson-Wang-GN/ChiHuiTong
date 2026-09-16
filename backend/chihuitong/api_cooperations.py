from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .api import StrictSerializer, paginated, validated
from .api_catalog import ClinicInput, VersionInput
from .identity import request_actor
from .services import cooperations


class CooperationInput(StrictSerializer):
    credit_code = serializers.CharField(max_length=18)
    name = serializers.CharField(max_length=160)
    kind = serializers.ChoiceField(choices=["single", "chain"])
    admin_name = serializers.CharField(max_length=100)
    admin_phone = serializers.CharField(max_length=40)


class ContactInput(StrictSerializer):
    name = serializers.CharField(max_length=100)
    phone = serializers.CharField(max_length=40)


class AgreementInput(StrictSerializer):
    number = serializers.CharField(max_length=80)
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    payment_mode = serializers.ChoiceField(choices=["instant", "postpaid"])
    settlement_cycle = serializers.ChoiceField(choices=["", "weekly", "monthly"])
    contact = ContactInput()
    clinic_ids = serializers.ListField(
        child=serializers.UUIDField(), allow_empty=True, max_length=1000
    )
    product_ids = serializers.ListField(
        child=serializers.UUIDField(), min_length=1, max_length=1000
    )
    attachment_ids = serializers.ListField(
        child=serializers.CharField(max_length=36), min_length=1, max_length=30
    )


class AgreementUpdate(VersionInput):
    data = AgreementInput()


class StartInput(StrictSerializer):
    cooperation_id = serializers.UUIDField(required=False)
    subject = CooperationInput(required=False)
    data = AgreementInput()


class OnboardingClinicInput(ClinicInput):
    admin_name = serializers.CharField(max_length=100, required=False)
    admin_phone = serializers.CharField(max_length=40, required=False)


class OnboardingInput(StrictSerializer):
    clinic = OnboardingClinicInput()
    agreement = AgreementInput()
    subject = CooperationInput(required=False)
    clinic_id = serializers.UUIDField(required=False)
    version = serializers.IntegerField(min_value=1, required=False)


@api_view(["POST"])
def onboarding_submit(request):
    from .api_sales import command
    from .services import onboarding

    actor = request_actor(request)
    data = validated(OnboardingInput, request)
    return Response(
        command(
            request,
            actor,
            "onboarding.submit",
            data,
            lambda: agreement_projection(actor, onboarding.submit(actor, **data)),
        ),
        status=201,
    )


@api_view(["GET", "POST"])
def unified_contracts(request):
    from django.db.models import Q

    from .api_catalog import contract_projection
    from .api_sales import command
    from .errors import require
    from .models import ClinicAgreement, ContractVersion
    from .services import contracts

    actor = request_actor(request)
    if request.method == "POST":
        data = validated(StartInput, request)
        return Response(
            command(
                request,
                actor,
                "agreement.start",
                data,
                lambda: agreement_projection(actor, cooperations.start_agreement(actor, **data)),
            ),
            status=201,
        )
    kind = request.query_params.get("kind", "clinic")
    require(
        kind in {"clinic", "resource", "channel", "legacy"}, "invalid_kind", "合同类型不合法", 400
    )
    word = request.query_params.get("search", "")[:160]
    if kind == "clinic":
        qs = ClinicAgreement.objects.select_related("cooperation__organization").filter(
            cooperation__in=cooperations.visible_cooperations(actor)
        )
        if word:
            qs = qs.filter(
                Q(number__icontains=word) | Q(cooperation__organization__name__icontains=word)
            )
        return paginated(
            request,
            qs,
            lambda item: agreement_projection(actor, item),
            states=["draft", "pending", "approved", "rejected", "terminated"],
        )
    qs = contracts.display_versions(
        ContractVersion.objects.select_related("contract__organization").filter(
            contract__in=contracts.accessible_contracts(actor),
            contract__kind="clinic" if kind == "legacy" else kind,
        )
    )
    if word:
        qs = qs.filter(
            Q(contract__number__icontains=word) | Q(contract__organization__name__icontains=word)
        )
    return paginated(
        request,
        qs,
        contract_projection,
        status_field="display_status",
        states=[
            "draft",
            "pending",
            "effective",
            "not_started",
            "expired",
            "superseded",
            "rejected",
            "terminated",
        ],
    )


class PaperInput(StrictSerializer):
    outbound_carrier = serializers.CharField(max_length=100, required=False)
    outbound_tracking = serializers.CharField(max_length=100, required=False)
    recipient = serializers.CharField(max_length=100, required=False)
    recipient_phone = serializers.CharField(max_length=40, required=False)
    return_address = serializers.CharField(max_length=500, required=False)
    received_at = serializers.DateTimeField(required=False)
    platform_signed_at = serializers.DateTimeField(required=False)
    return_carrier = serializers.CharField(max_length=100, required=False)
    return_tracking = serializers.CharField(max_length=100, required=False)
    returned_at = serializers.DateTimeField(required=False)
    signed_attachment_ids = serializers.ListField(
        child=serializers.CharField(max_length=36), required=False, min_length=1, max_length=30
    )


class PaperUpdate(VersionInput):
    data = PaperInput()


class ReviewInput(VersionInput):
    approved = serializers.BooleanField()
    final = serializers.BooleanField(default=False)
    reason = serializers.CharField(max_length=500)


class ReasonInput(VersionInput):
    reason = serializers.CharField(max_length=500)


class AttachInput(VersionInput):
    clinic_id = serializers.UUIDField()
    reason = serializers.CharField(max_length=500)


class BatchInput(StrictSerializer):
    clinic_ids = serializers.ListField(child=serializers.UUIDField(), min_length=1, max_length=100)
    reason = serializers.CharField(max_length=500)


def subject_projection(actor, item):
    from .services.clinics import visible_clinics

    return {
        "id": str(item.id),
        "organization_id": str(item.organization_id),
        "name": item.organization.name,
        "kind": item.kind,
        "status": item.status,
        "version": item.version,
        "can_manage": cooperations.full_access(actor, item),
        "clinic_count": item.clinics.filter(pk__in=visible_clinics(actor).values("id")).count(),
        "payment_mode": "instant" if item.kind == "single" else "postpaid",
    }


def agreement_projection(actor, item):
    from .services.clinics import visible_clinics

    full = cooperations.full_access(actor, item.cooperation, item)
    stores = item.coverage.select_related("clinic__organization").filter(
        clinic__in=visible_clinics(actor)
    )
    return {
        "id": str(item.id),
        "cooperation_id": str(item.cooperation_id),
        "subject_name": item.cooperation.organization.name,
        "onboarding": bool(item.onboarding_change_id),
        "onboarding_change_id": str(item.onboarding_change_id)
        if item.onboarding_change_id
        else None,
        "onboarding_clinic_id": str(item.onboarding_change.clinic_id)
        if item.onboarding_change_id
        else None,
        "onboarding_profile": item.onboarding_change.after
        if item.onboarding_change_id and full
        else None,
        "number": item.number,
        "revision": item.revision,
        "version": item.version,
        "status": item.status,
        "starts_at": item.starts_at.isoformat(),
        "ends_at": item.ends_at.isoformat(),
        "payment_mode": item.payment_mode,
        "settlement_cycle": item.settlement_cycle,
        "product_ids": item.product_ids,
        "contact": item.contact if full else {},
        "attachment_ids": item.attachment_ids if full else [],
        "signed_attachment_ids": item.signed_attachment_ids if full else [],
        "paper": item.paper if full else {},
        "content_status": item.content_status,
        "can_manage": full,
        "reason": item.reason if full else "",
        "due_at": item.due_at.isoformat() if item.due_at else None,
        "coverage": [
            {"id": str(link.clinic_id), "name": link.clinic.organization.name} for link in stores
        ],
        "scope_notice": "" if full else "仅展示负责门店的适用条款，不展示整份合同附件及其他门店",
    }


@api_view(["GET"])
def cooperation_list(request):
    actor = request_actor(request)
    qs = cooperations.visible_cooperations(actor)
    if request.query_params.get("search"):
        qs = qs.filter(organization__name__icontains=request.query_params["search"][:160])
    return paginated(
        request, qs, lambda value: subject_projection(actor, value), states=["active", "disabled"]
    )


@api_view(["GET"])
def cooperation_detail(request, cooperation_id):
    actor = request_actor(request)
    return Response(subject_projection(actor, cooperations.get_cooperation(actor, cooperation_id)))


@api_view(["POST"])
def attach(request, cooperation_id):
    from .api_catalog import clinic_projection

    return Response(
        clinic_projection(
            cooperations.attach_clinic(
                request_actor(request), cooperation_id, **validated(AttachInput, request)
            )
        )
    )


@api_view(["GET", "POST"])
def agreements(request, cooperation_id):
    actor = request_actor(request)
    item = cooperations.get_cooperation(actor, cooperation_id)
    if request.method == "POST":
        value = cooperations.save_agreement(
            actor, cooperation_id, data=validated(AgreementInput, request)
        )
        return Response(agreement_projection(actor, value), status=201)
    return paginated(
        request,
        item.agreements.select_related("cooperation__organization"),
        lambda value: agreement_projection(actor, value),
        states=["draft", "pending", "approved", "rejected", "terminated"],
    )


@api_view(["GET", "POST"])
def agreement_detail(request, agreement_id):
    actor = request_actor(request)
    item = cooperations.get_agreement(actor, agreement_id)
    if request.method == "POST":
        item = cooperations.save_agreement(
            actor, item.cooperation_id, agreement_id=item.id, **validated(AgreementUpdate, request)
        )
    return Response(agreement_projection(actor, item))


@api_view(["POST"])
def agreement_action(request, agreement_id, action):
    actor = request_actor(request)
    if action == "onboarding-review":
        from .services import onboarding

        item = onboarding.review(actor, agreement_id, **validated(ReviewInput, request))
    elif action == "submit":
        item = cooperations.submit_agreement(
            actor, agreement_id, **validated(VersionInput, request)
        )
    elif action == "terminate":
        item = cooperations.terminate_agreement(
            actor, agreement_id, **validated(ReasonInput, request)
        )
    elif action == "paper":
        data = validated(PaperUpdate, request)
        data["data"] = {
            k: v.isoformat() if hasattr(v, "isoformat") else v for k, v in data["data"].items()
        }
        item = cooperations.record_paper(actor, agreement_id, **data)
    else:
        from .errors import require

        require(action == "review", "not_found", "操作不存在", 404)
        item = cooperations.review_agreement(actor, agreement_id, **validated(ReviewInput, request))
    return Response(agreement_projection(actor, item))


@api_view(["POST"])
def batch_online(request):
    return Response(
        {
            "results": cooperations.batch_online(
                request_actor(request), **validated(BatchInput, request)
            )
        }
    )
