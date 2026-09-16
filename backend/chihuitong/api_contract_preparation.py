from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .api import StrictSerializer, paginated, validated
from .api_sales import command
from .identity import request_actor
from .models import ContractTemplate
from .services import contract_preparation as service


class DraftInput(StrictSerializer):
    kind = serializers.ChoiceField(choices=["single", "chain"])
    payload = serializers.JSONField()
    version = serializers.IntegerField(min_value=1, required=False)


class VersionInput(StrictSerializer):
    version = serializers.IntegerField(min_value=1)


class SignedInput(VersionInput):
    generation = serializers.IntegerField(min_value=1)
    attachment_ids = serializers.ListField(
        child=serializers.UUIDField(), min_length=1, max_length=20
    )


class TemplateInput(StrictSerializer):
    kind = serializers.ChoiceField(choices=["single", "chain"])
    title = serializers.CharField(max_length=160)
    body = serializers.CharField(max_length=30000)
    platform_name = serializers.CharField(max_length=160)
    platform_credit_code = serializers.RegexField(r"^[0-9A-HJ-NPQRTUWXY]{18}$")
    confirmed = serializers.BooleanField()


def projection(item):
    printed = item.prints.filter(revision=item.generation).first()
    return {
        "id": str(item.id),
        "version": item.version,
        "number": item.number,
        "kind": item.kind,
        "status": item.status,
        "payload": item.payload,
        "generation": item.generation,
        "signed_ids": item.signed_ids,
        "signed_generation": item.signed_generation,
        "generated_file_id": str(printed.asset_id) if printed else None,
        "print_changed": bool(printed and printed.snapshot.get("input") != service.contract_input(item.payload)),
        "agreement_id": str(item.agreement_id) if item.agreement_id else None,
        "created_at": item.created_at.isoformat(),
    }


@api_view(["GET", "POST"])
def drafts(request):
    actor = request_actor(request)
    if request.method == "POST":
        data = validated(DraftInput, request)
        return Response(
            command(
                request,
                actor,
                "contract_draft.create",
                data,
                lambda: projection(service.save(actor, **data)),
            ),
            status=201,
        )
    return paginated(request, service.visible(actor), projection, states=["draft", "submitted"])


@api_view(["GET", "POST"])
def detail(request, preparation_id):
    actor = request_actor(request)
    if request.method == "POST":
        data = validated(DraftInput, request)
        return Response(
            command(
                request,
                actor,
                "contract_draft.update",
                {**data, "id": str(preparation_id)},
                lambda: projection(service.save(actor, pk=preparation_id, **data)),
            )
        )
    return Response(projection(service.get(actor, preparation_id)))


@api_view(["POST"])
def action(request, preparation_id, action):
    from .errors import require

    actor = request_actor(request)
    require(action in {"generate", "sign", "submit"}, "not_found", "操作不存在", 404)
    data = validated(SignedInput if action == "sign" else VersionInput, request)
    if "attachment_ids" in data:
        data["attachment_ids"] = [str(x) for x in data["attachment_ids"]]
    handler = {"generate": service.generate, "sign": service.sign, "submit": service.submit}[action]
    return Response(
        command(
            request,
            actor,
            "contract_draft." + action,
            {**data, "id": str(preparation_id)},
            lambda: projection(handler(actor, preparation_id, **data)),
        )
    )


@api_view(["GET", "POST"])
def templates(request):
    actor = request_actor(request)
    actor.require_platform()
    if request.method == "POST":
        data = validated(TemplateInput, request)
        return Response(
            command(
                request,
                actor,
                "contract_template.publish",
                data,
                lambda: {"id": str(service.template(actor, **data).id)},
            ),
            status=201,
        )
    return paginated(
        request,
        ContractTemplate.objects.all(),
        lambda x: {
            "id": str(x.id),
            "kind": x.kind,
            "title": x.title,
            "body": x.body,
            "platform_name": x.platform_name,
            "platform_credit_code": x.platform_credit_code,
            "status": x.status,
            "created_at": x.created_at.isoformat(),
        },
        states=["active", "retired"],
    )
