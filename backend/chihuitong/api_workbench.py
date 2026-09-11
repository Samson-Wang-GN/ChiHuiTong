from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .identity import request_actor
from .api import api_prefix
from .services import workbench


def task_links(request, data):
    for row in data["results"]:
        row["detail_endpoint"] = row["detail_endpoint"].replace("/api/v1/", api_prefix(request) + "/", 1)
    return data


@api_view(["GET"])
def tasks(request):
    actor = request_actor(request)
    page = serializers.IntegerField(min_value=1).run_validation(request.query_params.get("page", 1))
    size = serializers.IntegerField(min_value=1, max_value=100).run_validation(
        request.query_params.get("page_size", 20)
    )
    return Response(
        task_links(request, workbench.list_tasks(
            actor,
            status=request.query_params.get("status", "pending"),
            category=request.query_params.get("category", "all"),
            page=page,
            page_size=size,
        ))
    )


@api_view(["GET"])
def task_detail(request, category, object_id):
    return Response(workbench.task_detail(request_actor(request), category, object_id))


@api_view(["GET"])
def overview(request):
    actor = request_actor(request)
    result = task_links(request, workbench.list_tasks(actor, page_size=5))
    return Response(
        {
            "organization_id": str(actor.organization.id),
            "organization_name": actor.organization.name,
            "kind": actor.organization.kind,
            "role": actor.membership.role,
            "tasks": result,
            "task_endpoint": api_prefix(request) + "/workbench/tasks",
        }
    )
