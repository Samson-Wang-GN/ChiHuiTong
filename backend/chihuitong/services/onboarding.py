"""A single submission/review for single-site onboarding, with atomic activation."""

from django.db import transaction

from chihuitong.errors import require
from chihuitong.models import ClinicProduct

from . import clinics, cooperations
from .common import advance, audit, check_version


@transaction.atomic
def submit(actor, *, clinic, agreement, subject=None, clinic_id=None, version=None):
    if clinic_id:
        item = clinics.get_clinic(actor, clinic_id, lock=True, edit=True)
        check_version(item, version)
        require(
            item.profile_version == 0 and item.cooperation_id and item.cooperation.kind == "single",
            "invalid_state",
            "只可补正尚未完成入驻的单店",
        )
        cooperation = item.cooperation
        require(
            not cooperation.agreements.filter(status__in=["draft", "pending"]).exists(),
            "pending_application",
            "已有待处理申请",
        )
    else:
        require(
            clinic.get("admin_name") and clinic.get("admin_phone"),
            "admin_required",
            "请填写门诊管理员信息",
            400,
        )
        require(
            subject and subject["kind"] == "single",
            "single_required",
            "单店联合入驻须填写单店签约主体",
            400,
        )
        cooperation = cooperations.create_cooperation(actor, **subject)
        item = clinics.create_clinic(actor, cooperation_id=cooperation.id, **clinic)
    change = clinics.submit_profile(actor, item.id, profile=clinic["profile"], version=item.version)
    data = {
        **agreement,
        "clinic_ids": [str(item.id)],
        "payment_mode": "instant",
        "settlement_cycle": "",
    }
    contract = cooperations.save_agreement(actor, cooperation.id, data=data)
    contract.onboarding_change = change
    advance(contract, "onboarding_change")
    contract = cooperations.submit_agreement(actor, contract.id, version=contract.version)
    audit(actor, contract, "onboarding.submitted", clinic_id=str(item.id), change_id=str(change.id))
    return contract


@transaction.atomic
def review(actor, agreement_id, *, version, approved, reason, final=False):
    actor.require_platform()
    ref = cooperations.get_agreement(actor, agreement_id)
    require(ref.onboarding_change_id, "invalid_state", "此记录不是单店联合入驻申请")
    # Common lock order: subject, clinic, agreement/profile. All final updates roll back together.
    cooperations.get_cooperation(actor, ref.cooperation_id, lock=True)
    clinic = clinics.get_clinic(actor, ref.onboarding_change.clinic_id, lock=True)
    contract = cooperations.get_agreement(actor, agreement_id, lock=True)
    check_version(contract, version)
    change = contract.onboarding_change
    require(
        contract.status == "pending" and change.status == "pending",
        "invalid_state",
        "申请已处理，请刷新",
    )
    if not approved or final:
        clinics.review_profile(
            actor, change.id, approved=approved, version=change.version, reason=reason, joint=True
        )
    contract = cooperations.review_agreement(
        actor,
        contract.id,
        version=contract.version,
        approved=approved,
        reason=reason,
        final=final,
        joint=True,
    )
    if approved and final:
        clinic.refresh_from_db()
        for product_id in contract.product_ids:
            clinics.assert_new_business(clinic, product_id)
            link, _ = ClinicProduct.objects.get_or_create(clinic=clinic, product_id=product_id)
            link.status = "online"
            advance(link, "status")
        clinics.set_service_status(
            actor, clinic.id, status="online", version=clinic.version, reason=reason
        )
    audit(actor, contract, "onboarding.reviewed", reason=reason, final=final, approved=approved)
    return contract
