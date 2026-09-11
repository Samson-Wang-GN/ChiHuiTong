from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .api import StrictSerializer, paginated
from .crypto import digest, normalize_phone
from .errors import require
from .exports import excel_response
from .identity import request_actor
from .models import Customer, Organization, Product
from .services import metrics
from .services.common import RESOURCE_KINDS, audit


class OverviewQuery(StrictSerializer):
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    as_of = serializers.DateTimeField(required=False)
    recorded_cutoff = serializers.DateTimeField(required=False)
    resource_id = serializers.UUIDField(required=False)
    product_id = serializers.UUIDField(required=False)
    mode = serializers.ChoiceField(choices=["all", "named", "physical"], default="all")
    metric = serializers.ChoiceField(
        choices=sorted(metrics.COUNTS | metrics.RATES.keys()), default="purchased"
    )
    component = serializers.ChoiceField(choices=["numerator", "denominator"], default="numerator")
    trend_from = serializers.DateField(required=False)
    trend_to = serializers.DateField(required=False)
    granularity = serializers.ChoiceField(choices=["day", "week", "month"], default="day")
    display = serializers.ChoiceField(choices=["cumulative", "net"], default="cumulative")
    status = serializers.CharField(max_length=30, default="all")
    page = serializers.IntegerField(min_value=1, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=100, default=20)
    search = serializers.CharField(max_length=100, required=False, allow_blank=True)
    customer_id = serializers.UUIDField(required=False)


def context(request):
    actor = request_actor(request)
    form = OverviewQuery(data=request.query_params.dict())
    form.is_valid(raise_exception=True)
    params = form.validated_data
    today = timezone.localdate()
    cohort = metrics.Cohort(
        actor,
        **{
            key: params[key]
            for key in ["as_of", "recorded_cutoff", "resource_id", "product_id", "mode"]
            if key in params
        },
        date_from=params.get("date_from", today - timedelta(days=29)),
        date_to=params.get("date_to", today),
    )
    return actor, cohort, params


@api_view(["GET"])
def overview(request):
    actor, cohort, _ = context(request)
    return Response(
        {
            "context": cohort.context(),
            "metrics": cohort.summary(),
            "resources": list(
                Organization.objects.filter(kind__in=RESOURCE_KINDS).values("id", "name")
            )
            if actor.platform
            else [{"id": str(actor.organization.id), "name": actor.organization.name}],
        }
    )


@api_view(["GET"])
def products(request):
    _, cohort, params = context(request)
    qs = Product.objects.filter(pk__in=cohort.base_cards.values("order__product_id"))
    if params.get("search"):
        qs = qs.filter(internal_name__icontains=params["search"])
    response = paginated(
        request,
        qs,
        lambda item: {
            "id": str(item.id),
            "internal_name": item.internal_name,
            "external_name": item.external_name,
            "status": item.status,
            **cohort.summary(product_id=item.id),
        },
        states=["active", "disabled"],
    )
    response.data["context"] = cohort.context()
    return response


@api_view(["GET"])
def trend(request):
    _, cohort, params = context(request)
    return Response(
        {
            "context": cohort.context(),
            **cohort.trend(
                metric=params["metric"],
                date_from=params.get("trend_from", cohort.date_from),
                date_to=params.get("trend_to", timezone.localdate(cohort.as_of)),
                granularity=params["granularity"],
                display=params["display"],
            ),
        }
    )


def detail_query(cohort, params, *, customer_cards=False):
    if customer_cards:
        require(params.get("customer_id"), "customer_required", "请指定客户", 400)
        kind, qs = "card", cohort.cards().filter(bound_customer=str(params["customer_id"]))
    else:
        kind, qs = cohort.details(params["metric"], component=params["component"])
    search = params.get("search", "").strip()
    if search:
        # Encrypted identity fields are not searched with plaintext SQL. Phone is exact HMAC lookup.
        if kind == "card":
            require(search.isdigit(), "invalid_search", "卡片明细请使用完整卡号搜索", 400)
            qs = qs.filter(serial=int(search))
        else:
            if search.upper().startswith("C"):
                customers = Customer.objects.filter(number=search.upper())
            else:
                customers = Customer.objects.filter(
                    phone_index=digest(normalize_phone(search), purpose="phone")
                )
            lookup = (
                "pk__in"
                if kind == "customer"
                else "customer__in"
                if kind == "appointment"
                else "appointment__customer__in"
            )
            qs = qs.filter(**{lookup: customers})
    if kind == "card":
        qs = qs.select_related("order__product")
    elif kind == "appointment":
        qs = qs.select_related("benefit__card__order__product", "customer", "clinic__organization")
    elif kind == "redemption":
        qs = qs.select_related(
            "appointment__benefit__card__order__product",
            "appointment__customer",
            "appointment__clinic__organization",
        )
    return kind, qs


@api_view(["GET"])
def details(request, customer_cards=False):
    _, cohort, params = context(request)
    kind, qs = detail_query(cohort, params, customer_cards=customer_cards)
    states = {
        "card": ["unclaimed", "activated", "voided"],
        "appointment": ["pending", "success", "completed"],
        "redemption": ["active"],
        "customer": ["related"],
    }
    response = paginated(
        request,
        qs,
        lambda item: metrics.detail_projection(kind, item, cohort),
        status_field="snapshot_status",
        states=states[kind],
    )
    response.data.update(
        {
            "context": cohort.context(),
            "kind": kind,
            "metric": params["metric"],
            "component": params["component"],
        }
    )
    return response


@api_view(["GET"])
def export(request):
    actor, cohort, params = context(request)
    kind, qs = detail_query(cohort, params)
    state = params["status"]
    require(
        state
        in {
            "all",
            "unclaimed",
            "activated",
            "voided",
            "pending",
            "success",
            "completed",
            "active",
            "related",
        },
        "invalid_status",
        "明细状态不合法",
        400,
    )
    if state != "all":
        qs = qs.filter(snapshot_status=state)
    keys = [
        "id",
        "status",
        "customer_number",
        "name",
        "phone",
        "card_id",
        "serial",
        "order_id",
        "product_id",
        "internal_name",
        "appointment_id",
        "completion_source",
        "units",
        "clinic_settled",
    ]
    headers = [
        "记录编号",
        "观察时点状态",
        "系统客户编号",
        "客户姓名",
        "手机号",
        "卡片编号",
        "卡号",
        "销售订单编号",
        "推广产品编号",
        "推广产品内部名称",
        "预约编号",
        "完成来源",
        "消耗份数",
        "门诊是否结清",
    ]

    def rows():
        for item in qs.order_by("created_at", "id").iterator(chunk_size=500):
            projection = metrics.detail_projection(kind, item, cohort)
            yield [projection.get(key) for key in keys]

    audit(
        actor,
        actor.organization,
        "metrics.details_exported",
        metric=params["metric"],
        component=params["component"],
        count=qs.count(),
        context=cohort.context(),
    )
    return excel_response(headers, rows(), filename="customer-overview-details.xlsx")
