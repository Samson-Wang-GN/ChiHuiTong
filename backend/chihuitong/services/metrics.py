"""REQ-029: one authorized issue cohort, replayed using immutable business facts."""

from datetime import datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import (
    Case,
    CharField,
    Count,
    Exists,
    OuterRef,
    Q,
    Subquery,
    Sum,
    Value,
    When,
)
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, Coalesce
from django.utils import timezone

from chihuitong.errors import require
from chihuitong.models import Appointment, Card, Customer, DomainEvent, Redemption

from .common import RESOURCE_KINDS
from .sales import visible_orders

RATES = {
    "activation_rate": ("activated", "purchased"),
    "appointment_rate": ("appointment_people", "activated_people"),
    "redemption_rate": ("redemption_people", "appointment_people"),
}
COUNTS = {
    "customers",
    "purchased",
    "voided",
    "activated",
    "appointments",
    "redemptions",
    "activated_people",
    "appointment_people",
    "redemption_people",
    "redemption_units",
}


def midnight(day):
    return timezone.make_aware(datetime.combine(day, time.min))


def rate(numerator, denominator):
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": str(
            (Decimal(numerator) * 100 / denominator).quantize(
                Decimal("0.1"), rounding=ROUND_HALF_UP
            )
        )
        if denominator
        else None,
        "unit": "%",
    }


class Cohort:
    def __init__(
        self,
        actor,
        *,
        date_from,
        date_to,
        as_of=None,
        recorded_cutoff=None,
        resource_id=None,
        product_id=None,
        mode="all",
    ):
        require(
            actor.platform or actor.organization.kind in RESOURCE_KINDS,
            "forbidden",
            "此概览仅向平台及客户资源方开放",
            403,
        )
        now = timezone.now()
        as_of = as_of or now
        recorded_cutoff = recorded_cutoff or now
        require(
            timezone.is_aware(as_of) and as_of <= now,
            "invalid_observation",
            "观察时间不能晚于当前时间",
            400,
        )
        require(
            timezone.is_aware(recorded_cutoff) and recorded_cutoff <= now,
            "invalid_observation",
            "事实入账观察时间不能晚于当前时间",
            400,
        )
        require(
            date_from <= date_to <= timezone.localdate(now)
            and mode in {"all", "named", "physical"},
            "invalid_cohort",
            "开卡日期或销售方式不合法",
            400,
        )
        self.actor, self.date_from, self.date_to = actor, date_from, date_to
        self.as_of, self.recorded_cutoff = as_of, recorded_cutoff
        self.resource_id, self.product_id, self.mode = resource_id, product_id, mode
        orders = visible_orders(actor).filter(
            approved_at__gte=midnight(date_from),
            approved_at__lt=midnight(date_to + timedelta(days=1)),
        )
        if resource_id:
            require(
                actor.platform or str(resource_id) == str(actor.organization.id),
                "forbidden",
                "不能查询其他资源方概览",
                403,
            )
            orders = orders.filter(organization_id=resource_id)
        if product_id:
            orders = orders.filter(product_id=product_id)
        if mode != "all":
            orders = orders.filter(mode=mode)
        self.base_cards = Card.objects.filter(order__in=orders)

    def context(self):
        return {
            "date_from": self.date_from.isoformat(),
            "date_to": self.date_to.isoformat(),
            "as_of": self.as_of.isoformat(),
            "recorded_cutoff": self.recorded_cutoff.isoformat(),
            "resource_id": str(self.resource_id) if self.resource_id else None,
            "product_id": str(self.product_id) if self.product_id else None,
            "mode": self.mode,
            "cohort_basis": "issued_batch",
            "timezone": "Asia/Shanghai",
            "identity_labels": "current_authorized_customer_profile",
        }

    def events(self, at):
        return DomainEvent.objects.filter(
            occurred_at__lte=at, recorded_at__lte=self.recorded_cutoff
        )

    def cards(self, at=None, product_id=None):
        at = at or self.as_of
        events = self.events(at).filter(card_id=OuterRef("pk"))
        issued = events.filter(kind="issued")
        binding = events.filter(kind__in=["issued", "activated"]).order_by("-occurred_at", "-id")
        qs = self.base_cards.annotate(
            has_issuance=Exists(issued),
            is_voided=Exists(events.filter(kind="voided")),
            is_activated=Exists(events.filter(kind="activated")),
            bound_customer=Subquery(
                binding.annotate(customer_text=KeyTextTransform("customer_id", "payload")).values(
                    "customer_text"
                )[:1],
                output_field=CharField(),
            ),
        ).filter(has_issuance=True)
        if product_id:
            qs = qs.filter(order__product_id=product_id)
        return qs.annotate(
            snapshot_status=Case(
                When(is_voided=True, then=Value("voided")),
                When(is_activated=True, then=Value("activated")),
                default=Value("unclaimed"),
                output_field=CharField(),
            )
        )

    def appointments(self, cards=None, at=None):
        at = at or self.as_of
        cards = self.cards(at) if cards is None else cards
        events = (
            self.events(at)
            .filter(kind="appointment.state", object_id=OuterRef("pk"))
            .order_by("-occurred_at", "-id")
        )
        return (
            Appointment.objects.filter(
                benefit__card__in=cards.filter(is_voided=False, is_activated=True)
            )
            .annotate(
                snapshot_status=Subquery(
                    events.annotate(text=KeyTextTransform("status", "payload")).values("text")[:1],
                    output_field=CharField(),
                ),
                snapshot_completion=Subquery(
                    events.annotate(text=KeyTextTransform("completion_source", "payload")).values(
                        "text"
                    )[:1],
                    output_field=CharField(),
                ),
            )
            .exclude(snapshot_status__isnull=True)
        )

    def redemptions(self, cards=None, at=None):
        at = at or self.as_of
        cards = self.cards(at) if cards is None else cards
        events = (
            self.events(at)
            .filter(kind__in=["redemption.active", "redemption.reversed"], object_id=OuterRef("pk"))
            .order_by("-occurred_at", "-id")
        )
        return (
            Redemption.objects.filter(
                appointment__benefit__card__in=cards.filter(is_voided=False, is_activated=True)
            )
            .annotate(
                snapshot_event=Subquery(events.values("kind")[:1]),
            )
            .exclude(snapshot_event__isnull=True)
            .annotate(
                snapshot_status=Case(
                    When(snapshot_event="redemption.active", then=Value("active")),
                    default=Value("reversed"),
                    output_field=CharField(),
                )
            )
        )

    def summary(self, *, at=None, product_id=None):
        at = at or self.as_of
        cards = self.cards(at, product_id)
        result = cards.aggregate(
            customers=Count("bound_customer", distinct=True),
            purchased=Count("pk", filter=Q(is_voided=False)),
            voided=Count("pk", filter=Q(is_voided=True)),
            activated=Count("pk", filter=Q(is_voided=False, is_activated=True)),
            activated_people=Count(
                "bound_customer", distinct=True, filter=Q(is_voided=False, is_activated=True)
            ),
        )
        appts = self.appointments(cards, at).filter(
            snapshot_status__in=["pending", "success", "completed"]
        )
        result.update(
            appts.aggregate(
                appointments=Count("pk"), appointment_people=Count("customer_id", distinct=True)
            )
        )
        redeemed = self.redemptions(cards, at).filter(snapshot_status="active")
        result.update(
            redeemed.aggregate(
                redemptions=Count("pk"),
                redemption_people=Count("appointment__customer_id", distinct=True),
                redemption_units=Coalesce(Sum("units"), 0),
            )
        )
        result.update({key: rate(result[num], result[den]) for key, (num, den) in RATES.items()})
        result["quality_warnings"] = [
            key for key in RATES if result[key]["numerator"] > result[key]["denominator"]
        ]
        missing = self.base_cards.filter(created_at__lte=at).exclude(pk__in=cards.values("pk"))
        if product_id:
            missing = missing.filter(order__product_id=product_id)
        result["excluded_missing_issuance"] = missing.count()
        return result

    def trend(self, *, metric, date_from, date_to, granularity, display="cumulative"):
        require(
            metric in COUNTS | RATES.keys()
            and granularity in {"day", "week", "month"}
            and display in {"cumulative", "net"},
            "invalid_trend",
            "趋势指标或显示方式不合法",
            400,
        )
        require(
            date_from <= date_to <= timezone.localdate(self.as_of),
            "invalid_trend_range",
            "趋势日期不能晚于观察时间",
            400,
        )
        periods = []
        start = date_from
        while start <= date_to:
            if granularity == "day":
                next_date = start + timedelta(days=1)
            elif granularity == "week":
                next_date = start + timedelta(days=7 - start.weekday())
            else:
                next_date = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
            end = min(date_to, next_date - timedelta(days=1))
            periods.append((start, end))
            require(
                len(periods) <= 366,
                "too_many_points",
                "单次趋势最多366个点，请缩小日期范围或按周/月查看",
                400,
            )
            start = next_date
        previous = self.summary(at=midnight(date_from) - timedelta(microseconds=1))
        points = []
        for start, end in periods:
            cutoff = min(self.as_of, midnight(end + timedelta(days=1)) - timedelta(microseconds=1))
            current = self.summary(at=cutoff)
            value = current[metric]
            if metric in COUNTS and display == "net":
                value -= previous[metric]
            points.append(
                {
                    "from": start.isoformat(),
                    "to": end.isoformat(),
                    "as_of": cutoff.isoformat(),
                    "value": value,
                }
            )
            previous = current
        return {
            "metric": metric,
            "granularity": granularity,
            "display": "ratio" if metric in RATES else display,
            "points": points,
        }

    def details(self, metric, *, component="numerator"):
        require(
            metric in COUNTS | RATES.keys() and component in {"numerator", "denominator"},
            "invalid_metric",
            "明细指标不合法",
            400,
        )
        if metric in RATES:
            metric = RATES[metric][component == "denominator"]
        cards = self.cards()
        if metric in {"purchased", "voided", "activated", "activated_people"}:
            cards = cards.filter(is_voided=(metric == "voided"))
            if metric in {"activated", "activated_people"}:
                cards = cards.filter(is_activated=True)
        if metric in {"customers", "activated_people"}:
            return "customer", Customer.objects.annotate(
                customer_uuid=Cast("pk", CharField())
            ).filter(customer_uuid__in=cards.values("bound_customer")).annotate(
                snapshot_status=Value("related", output_field=CharField())
            )
        if metric in {"appointment_people", "redemption_people"}:
            ids = (
                self.appointments()
                .filter(snapshot_status__in=["pending", "success", "completed"])
                .values("customer_id")
                if metric == "appointment_people"
                else self.redemptions()
                .filter(snapshot_status="active")
                .values("appointment__customer_id")
            )
            return "customer", Customer.objects.filter(pk__in=ids).annotate(
                snapshot_status=Value("related", output_field=CharField())
            )
        if metric == "appointments":
            return "appointment", self.appointments().filter(
                snapshot_status__in=["pending", "success", "completed"]
            )
        if metric in {"redemptions", "redemption_units"}:
            return "redemption", self.redemptions().filter(snapshot_status="active")
        return "card", cards


def detail_projection(kind, item, cohort):
    base = {"id": str(item.id), "status": item.snapshot_status}
    if kind == "customer":
        # The drilldown never returns unrelated cards of a shared customer.
        return {
            **base,
            "customer_number": item.number,
            "name": item.name,
            "phone": item.phone,
            "profile": {key: item.profile.get(key) for key in ["gender", "age", "occupation"]},
            "cards_endpoint": "/api/v1/customer-overview/customer-cards",
            "customer_id": str(item.id),
        }
    card = (
        item
        if kind == "card"
        else item.benefit.card
        if kind == "appointment"
        else item.appointment.benefit.card
    )
    base.update(
        {
            "card_id": str(card.id),
            "serial": str(card.serial),
            "order_id": str(card.order_id),
            "product_id": str(card.order.product_id),
            "internal_name": card.order.product.internal_name,
            "resource_id": str(card.order.organization_id),
        }
    )
    if kind == "card":
        base["customer_id"] = item.bound_customer
    else:
        appointment = item if kind == "appointment" else item.appointment
        base.update(
            {
                "appointment_id": str(appointment.id),
                "customer_id": str(appointment.customer_id),
                "customer_number": appointment.customer.number,
                "name": appointment.customer.name,
                "phone": appointment.customer.phone,
                "clinic_name": appointment.clinic.organization.name,
            }
        )
        if kind == "appointment":
            base["completion_source"] = item.snapshot_completion
        else:
            base.update(
                {
                    "units": item.units,
                    "clinic_settled": bool(item.settled_at and item.settled_at <= cohort.as_of),
                }
            )
    return base
