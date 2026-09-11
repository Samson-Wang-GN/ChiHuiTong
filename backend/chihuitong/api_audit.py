from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .errors import require
from .identity import request_actor
from .models import AuditEvent, ClinicProfileChange, ContractVersion, Membership, Organization, Product, SourceBrand, SmsTemplate
from .services import appointments, clinics, contracts, finance, imports, organizations, sales


def scoped_object(actor, object_type, object_id):
    if object_type == "clinic":
        if actor.organization.kind == "clinic":
            actor.require_admin()
        return clinics.get_clinic(actor, object_id)
    if object_type == "clinicprofilechange":
        if actor.organization.kind == "clinic":
            actor.require_admin()
        query = ClinicProfileChange.objects.filter(clinic__in=clinics.visible_clinics(actor))
    elif object_type == "contract":
        query = contracts.accessible_contracts(actor)
    elif object_type == "contractversion":
        item = ContractVersion.objects.filter(pk=object_id, contract__in=contracts.accessible_contracts(actor)).first()
        require(item, "not_found", "合同版本不存在", 404)
        return item.contract
    elif object_type == "clinicbill":
        return finance.get_bill(actor, object_id)
    elif object_type == "partnerbill":
        return finance.get_partner_bill(actor, object_id)
    elif object_type == "salesorder":
        return sales.get_order(actor, object_id)
    elif object_type == "importbatch":
        return imports.get_import(actor, object_id)
    elif object_type == "appointment":
        query = appointments.visible_appointments(actor)
    elif object_type == "organization":
        return organizations.managed_org(actor, object_id)
    elif object_type == "membership":
        actor.require_admin()
        query = Membership.objects.all() if actor.platform else Membership.objects.filter(organization=actor.organization)
    elif object_type in {"product", "sourcebrand", "smstemplate"}:
        actor.require_platform()
        query = {"product": Product, "sourcebrand": SourceBrand, "smstemplate": SmsTemplate}[object_type].objects.all()
    else:
        require(False, "not_found", "不支持的日志对象", 404)
    item = query.filter(pk=object_id).first()
    require(item, "not_found", "记录不存在或无权查看", 404)
    return item


@api_view(["GET"])
def object_log(request, object_type, object_id):
    actor = request_actor(request)
    obj = scoped_object(actor, object_type, object_id)
    query = AuditEvent.objects.filter(object_type=obj._meta.model_name, object_id=obj.id)
    action = request.query_params.get("action", "")
    if action:
        query = query.filter(action=action[:80])
    page = serializers.IntegerField(min_value=1).run_validation(request.query_params.get("page", 1))
    size = serializers.IntegerField(min_value=1, max_value=100).run_validation(request.query_params.get("page_size", 20))
    return Response({"total": query.count(), "page": page, "page_size": size, "results": [
        {"id": str(item.id), "occurred_at": item.occurred_at.isoformat(), "action": item.action,
         "actor": item.actor_name or ("系统" if not item.actor_id else "历史未记录"),
         "organization": item.organization_name or ("系统" if not item.organization_id else "历史未记录"),
         "role": item.actor_role or None, "reason": item.reason, "metadata": item.metadata,
         "request_id": str(item.request_id) if item.request_id else None}
        for item in query.order_by("-id")[(page - 1) * size:page * size]
    ]})
