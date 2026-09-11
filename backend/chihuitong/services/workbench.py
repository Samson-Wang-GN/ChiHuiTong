from dataclasses import dataclass

from django.db.models import Case, CharField, DateTimeField, F, Q, Value, When
from django.db.models.functions import Cast, Concat
from django.utils import timezone

from chihuitong.errors import require
from chihuitong.models import (
    ClinicProfileChange,
    ClinicReceipt,
    ContractVersion,
    FinanceFeedback,
    FulfillmentTask,
    Organization,
    Outbox,
    PartnerBill,
    PurchaseReceipt,
    Reschedule,
    SalesOrder,
)

from .appointments import visible_appointments
from .clinics import visible_clinics
from .common import RESOURCE_KINDS
from .contracts import accessible_contracts
from .finance_queries import clinic_bills_with_status
from .sales import visible_orders


@dataclass
class TaskSource:
    code: str
    title: str
    queryset: object
    pending: Q
    actions: tuple
    due_field: str = ""

    def normalized(self, status):
        qs = self.queryset.annotate(
            task_state=Case(
                When(self.pending, then=Value("pending")),
                default=Value("processed"),
                output_field=CharField(),
            )
        )
        if status != "all":
            qs = qs.filter(task_state=status)
        return (
            qs.annotate(
                task_key=Concat(Value(self.code + ":"), Cast("pk", CharField())),
                task_id=Cast("pk", CharField()),
                task_kind=Value(self.code, output_field=CharField()),
                task_title=Value(self.title, output_field=CharField()),
                task_created=F("created_at"),
                task_due=F(self.due_field)
                if self.due_field
                else Cast(Value(None), DateTimeField()),
            )
            .order_by()
            .values(
                "task_key",
                "task_id",
                "task_kind",
                "task_title",
                "task_state",
                "task_created",
                "task_due",
            )
        )


def sources(actor):
    items = []
    clinics = visible_clinics(actor)
    if actor.platform:
        items.extend(
            [
                TaskSource(
                    "organization_review",
                    "合作机构审核",
                    Organization.objects.exclude(kind__in=["clinic", "platform"]),
                    Q(status="pending"),
                    ("review",),
                ),
                TaskSource(
                    "clinic_profile",
                    "门诊资料审核",
                    ClinicProfileChange.objects.all(),
                    Q(status="pending"),
                    ("review",),
                    "due_at",
                ),
                TaskSource(
                    "contract_review",
                    "合作合同审核",
                    ContractVersion.objects.exclude(status="draft"),
                    Q(status="pending"),
                    ("review",),
                    "due_at",
                ),
                TaskSource(
                    "sales_review",
                    "推广产品开卡审核",
                    SalesOrder.objects.filter(
                        status__in=["pending_approval", "issued", "rejected"]
                    ),
                    Q(status="pending_approval"),
                    ("review",),
                ),
                TaskSource(
                    "sales_stop",
                    "销售订单取消或停止申请",
                    SalesOrder.objects.filter(
                        status__in=["cancel_pending", "stop_pending", "cancelled", "stopped"]
                    ),
                    Q(status__in=["cancel_pending", "stop_pending"]),
                    ("stop-review",),
                ),
                TaskSource(
                    "purchase_receipt",
                    "采购付款凭证审核",
                    PurchaseReceipt.objects.all(),
                    Q(status="pending"),
                    ("review",),
                ),
                TaskSource(
                    "clinic_receipt",
                    "门诊付款凭证审核",
                    ClinicReceipt.objects.all(),
                    Q(status="pending"),
                    ("review",),
                ),
                TaskSource(
                    "partner_payment",
                    "合作方结算付款",
                    PartnerBill.objects.filter(
                        status__in=["pending_payment", "pending_receipt", "completed"]
                    ),
                    Q(status="pending_payment"),
                    ("pay",),
                    "due_at",
                ),
                TaskSource(
                    "finance_feedback",
                    "对账反馈处理",
                    FinanceFeedback.objects.all(),
                    Q(status="open"),
                    ("respond",),
                ),
                TaskSource(
                    "failed_job",
                    "后台任务异常",
                    Outbox.objects.filter(status__in=["failed", "done"]),
                    Q(status="failed"),
                    ("retry",),
                ),
            ]
        )
    if actor.organization.kind in RESOURCE_KINDS:
        items.append(
            TaskSource(
                "sales_payment",
                "推广产品采购付款",
                visible_orders(actor).filter(
                    status__in=["pending_payment", "issued", "cancelled", "rejected"]
                ),
                Q(status="pending_payment"),
                ("submit-receipt",),
            )
        )
    if actor.organization.kind == "channel":
        items.append(
            TaskSource(
                "contract_submission",
                "门诊三方合同签订与续签",
                ContractVersion.objects.filter(
                    contract__in=accessible_contracts(actor), contract__kind="clinic"
                ).exclude(status="pending"),
                Q(status__in=["draft", "rejected"]),
                ("edit", "submit"),
            )
        )
    if actor.organization.kind in {"channel", "clinic"} and (
        actor.organization.kind != "clinic" or actor.membership.role == "admin"
    ):
        items.append(
            TaskSource(
                "profile_resubmission",
                "门诊资料退回修改",
                ClinicProfileChange.objects.filter(clinic__in=clinics).exclude(status="pending"),
                Q(status="rejected"),
                ("resubmit",),
            )
        )
        bills = clinic_bills_with_status(actor)
        items.append(
            TaskSource(
                "clinic_payment" if actor.organization.kind == "clinic" else "clinic_collection",
                "门诊账单付款" if actor.organization.kind == "clinic" else "门诊账单催收",
                bills,
                Q(status="open"),
                ("pay", "submit-receipt")
                if actor.organization.kind == "clinic"
                else ("collection-note",),
                "due_at",
            )
        )
    if actor.organization.kind in RESOURCE_KINDS | {"channel"} and actor.membership.role == "admin":
        bills = PartnerBill.objects.filter(organization=actor.organization)
        items.append(
            TaskSource(
                "partner_confirmation",
                "合作结算确认及收款",
                bills.exclude(status__in=["pending_payment", "no_payment", "disputed"]),
                Q(status__in=["pending_confirmation", "pending_receipt"]),
                ("confirm", "receive", "feedback"),
                "due_at",
            )
        )
    if actor.organization.kind == "clinic":
        appointments = visible_appointments(actor)
        items.extend(
            [
                TaskSource(
                    "appointment_confirmation",
                    "预约确认",
                    appointments,
                    Q(status="pending"),
                    ("confirm", "cancel"),
                    "pending_deadline",
                ),
                TaskSource(
                    "appointment_reschedule",
                    "客户改期申请",
                    Reschedule.objects.filter(
                        appointment__in=appointments, initiated_by="customer"
                    ),
                    Q(status="pending"),
                    ("review",),
                    "expires_at",
                ),
                TaskSource(
                    "appointment_fulfillment",
                    "过期预约及补核销待办",
                    FulfillmentTask.objects.filter(appointment__in=appointments),
                    Q(status__in=["pending", "conflict"]),
                    ("redeem", "reschedule", "report-absent"),
                ),
            ]
        )
    return items


def list_tasks(actor, *, status="pending", category="all", page=1, page_size=20):
    require(
        status in {"pending", "processed", "all"}
        and type(page) is int
        and 1 <= page
        and type(page_size) is int
        and 1 <= page_size <= 100,
        "invalid_filter",
        "待办筛选或分页不合法",
        400,
    )
    selected = sources(actor)
    require(
        category == "all" or category in {source.code for source in selected},
        "invalid_category",
        "没有此角色的待办类型",
        400,
    )
    if category != "all":
        selected = [source for source in selected if source.code == category]
    counts = {"pending": 0, "processed": 0, "all": 0}
    categories = {}
    querysets = []
    for source in selected:
        total = source.queryset.count()
        pending = source.queryset.filter(source.pending).count()
        counts["pending"] += pending
        counts["processed"] += total - pending
        counts["all"] += total
        categories[source.code] = {"title": source.title, "pending": pending, "all": total}
        querysets.append(source.normalized(status))
    if not querysets:
        return {
            "results": [],
            "total": 0,
            "counts": counts,
            "categories": categories,
            "page": page,
            "page_size": page_size,
        }
    union = querysets[0].union(*querysets[1:], all=True).order_by("-task_created", "task_key")
    results = []
    for row in union[(page - 1) * page_size : page * page_size]:
        results.append(
            {
                "id": row["task_key"],
                "object_id": row["task_id"],
                "kind": row["task_kind"],
                "title": row["task_title"],
                "status": row["task_state"],
                "created_at": row["task_created"].isoformat(),
                "due_at": row["task_due"].isoformat() if row["task_due"] else None,
                "overdue": bool(
                    row["task_due"]
                    and row["task_due"] < timezone.now()
                    and row["task_state"] == "pending"
                ),
                "detail_endpoint": f"/api/v1/workbench/tasks/{row['task_kind']}/{row['task_id']}",
            }
        )
    return {
        "results": results,
        "total": counts[status],
        "counts": counts,
        "categories": categories,
        "page": page,
        "page_size": page_size,
    }


def task_detail(actor, category, object_id):
    source = next((item for item in sources(actor) if item.code == category), None)
    require(source, "not_found", "待办不存在", 404)
    obj = source.queryset.filter(pk=object_id).first()
    require(obj, "not_found", "待办不存在或无权访问", 404)
    pending = source.queryset.filter(pk=object_id).filter(source.pending).exists()
    from chihuitong.api_appointments import appointment_projection, reschedule_projection
    from chihuitong.api_catalog import change_projection, contract_projection
    from chihuitong.api_notifications import job_projection
    from chihuitong.api_sales import order_projection, receipt_projection

    from .finance_queries import (
        clinic_bill_projection,
        feedback_projection,
        partner_bill_projection,
    )
    from .finance_queries import receipt_projection as clinic_receipt_projection

    handlers = {
        "organization_review": lambda item: {
            "id": str(item.id),
            "name": item.name,
            "kind": item.kind,
            "status": item.status,
            "details": item.details,
            "version": item.version,
        },
        "clinic_profile": change_projection,
        "profile_resubmission": change_projection,
        "contract_review": contract_projection,
        "contract_submission": contract_projection,
        "sales_review": order_projection,
        "sales_stop": order_projection,
        "sales_payment": order_projection,
        "purchase_receipt": receipt_projection,
        "clinic_receipt": clinic_receipt_projection,
        "partner_payment": partner_bill_projection,
        "partner_confirmation": partner_bill_projection,
        "clinic_payment": clinic_bill_projection,
        "clinic_collection": clinic_bill_projection,
        "finance_feedback": feedback_projection,
        "failed_job": job_projection,
        "appointment_confirmation": lambda item: appointment_projection(actor, item),
        "appointment_reschedule": reschedule_projection,
        "appointment_fulfillment": lambda item: {
            "id": str(item.id),
            "kind": item.kind,
            "status": item.status,
            "appointment": appointment_projection(actor, item.appointment),
        },
    }
    actions = list(source.actions) if pending else []
    if category == "partner_confirmation":
        actions = (
            ["confirm", "feedback"]
            if obj.status == "pending_confirmation"
            else ["receive", "feedback"]
            if obj.status == "pending_receipt"
            else []
        )
    if category == "contract_submission" and obj.status == "rejected":
        actions = ["create-revision"]
    if category == "clinic_payment" and (
        obj.receipts.filter(status="pending").exists()
        or obj.payment_attempts.filter(status__in=["creating", "pending", "unknown"]).exists()
    ):
        actions = ["view-payment-progress"]
    if category == "appointment_fulfillment" and obj.status == "conflict":
        actions = ["view-conflict"]
    return {
        "kind": category,
        "title": source.title,
        "status": "pending" if pending else "processed",
        "record": handlers[category](obj),
        "actions": actions,
        "instruction": "调用对应业务接口处理，阅读此任务不会改变业务状态。",
    }
