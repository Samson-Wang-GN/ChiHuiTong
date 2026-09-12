"""Explicit, one-time synthetic scenarios in an isolated acceptance database."""

import io
from datetime import datetime, time, timedelta
from unittest.mock import patch

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageDraw

from chihuitong.acceptance import ACCOUNTS
from chihuitong.models import AuditEvent, Membership, Organization
from chihuitong.services import appointments, catalog, clinics, contracts, customers, files, finance, organizations, sales
from chihuitong.services.common import Actor, advisory_lock, audit


def asset(actor, purpose):
    image = Image.new("RGB", (640, 320), "white")
    draw = ImageDraw.Draw(image)
    draw.text((30, 140), "SYNTHETIC ACCEPTANCE SAMPLE - NOT A VALID DOCUMENT", fill="black")
    output = io.BytesIO()
    image.save(output, "PNG")
    return files.upload_file(actor, data=output.getvalue(), filename=f"演示非真实-{purpose}.png", purpose=purpose)


def agreement(platform, actor, owner, product, start):
    proof = asset(actor, "contract")
    item = contracts.create_version(actor, owner.id, number=f"DEMO-{owner.kind}", data={
        "starts_at": start - timedelta(days=10), "ends_at": start + timedelta(days=730),
        "settlement_cycle": "monthly", "contact": {"name": "演示合同联系人", "phone": ACCOUNTS["channel"][0]},
        "attachment_ids": [str(proof.id)],
    })
    if owner.kind != "clinic":
        contracts.save_term(platform, item.id, product_id=product.id, mode="percent", value="20", reason="合成验收条款")
    item = contracts.submit_version(actor, item.id, version=item.version)
    return contracts.review_version(platform, item.id, approved=True, version=item.version, reason="合成验收审核，不是真实合同")


def instant(date):
    return timezone.make_aware(datetime.combine(date, time(12)))


@transaction.atomic
def seed():
    if not settings.ACCEPTANCE_ENABLED or settings.ENVIRONMENT == "production" or not settings.DATABASES["default"]["NAME"].startswith("chihuitong_acceptance"):
        raise CommandError("仅允许独立、显式启用的合成验收库")
    advisory_lock("acceptance", "seed-v1")
    if AuditEvent.objects.filter(action="acceptance.seeded").exists():
        return False
    if Organization.objects.exists():
        raise CommandError("目标库非空且没有完整初始化标记；拒绝覆盖")
    now = timezone.now()
    current_month = timezone.localdate().replace(day=1)
    prior_month = (current_month - timedelta(days=1)).replace(day=1)
    start = instant(prior_month - timedelta(days=15))
    with patch("django.utils.timezone.now", return_value=start):
        org = Organization.objects.create(name="齿慧通演示平台", kind="platform")
        account = organizations.account_for(*ACCOUNTS["platform"])
        platform = Actor(Membership.objects.create(organization=org, account=account, role="admin", platform_created=True))
        actors = {}
        for role, kind, name in [("resource", "broker", "演示客户资源机构"), ("channel", "channel", "演示门诊渠道公司")]:
            phone, admin = ACCOUNTS[role]
            owner = organizations.create_organization(platform, name=name, kind=kind, admin_name=admin, admin_phone=phone)
            organizations.review_organization(platform, owner.id, approved=True, version=owner.version, reason="合成验收机构")
            actors[role] = Actor(Membership.objects.select_related("organization", "account").get(organization=owner))
        resource, channel = actors["resource"], actors["channel"]
        product = catalog.save_product(platform, {
            "internal_name": "演示·洁牙推广产品", "external_name": "舒心洁牙体验卡（演示）",
            "product_type": "service", "usage_rules": "仅演示：提前预约，每次消耗1份，不可兑换现金。",
            "redemption_units": 1, "fee_cents": 6000, "validity_days": 180, "status": "active",
        })
        for actor in [resource, channel]:
            agreement(platform, platform, actor.organization, product, start)
        license_image = asset(channel, "license")
        cover = asset(channel, "cover")
        profile = {"name": "演示口腔门诊", "legal_entity": "演示医疗机构（非真实）", "province": "北京市", "city": "北京市", "district": "海淀区", "address": "演示路1号（虚构）", "business_hours": "09:00-18:00", "frontdesk_phone": ACCOUNTS["clinic"][0], "business_contact": "演示门诊联系人", "business_phone": ACCOUNTS["clinic"][0], "responsible_id": str(channel.membership.id), "business_license_ids": [str(license_image.id)], "medical_license_ids": [str(license_image.id)], "cover_id": str(cover.id)}
        clinic = clinics.create_clinic(channel, channel_id=channel.organization.id, profile=profile, admin_phone=ACCOUNTS["clinic"][0], admin_name=ACCOUNTS["clinic"][1])
        change = clinics.submit_profile(channel, clinic.id, profile=profile, version=clinic.version)
        clinics.review_profile(platform, change.id, approved=True, version=change.version, reason="合成资质，不作为真实证明")
        clinic_actor = Actor(Membership.objects.select_related("organization", "account").get(organization=clinic.organization))
        agreement(platform, channel, clinic_actor.organization, product, start)
        clinic.refresh_from_db()
        clinics.set_service_status(platform, clinic.id, status="online", version=clinic.version, reason="演示门诊上线")
        clinics.set_clinic_product(channel, clinic.id, product_id=product.id, online=True, reason="演示产品上线")
        brand = catalog.save_brand(platform, resource.organization.id, name="演示保险客户福利")

    def sale(index, when, *, paid=False, physical=False, approve=True):
        with patch("django.utils.timezone.now", return_value=when):
            order = sales.create_order(resource, product_id=product.id, source_brand_id=brand.id, mode="physical" if physical else "named", entry="quantity" if physical else "single", quantity=6 if physical else None, rows=None if physical else [{"name": f"演示客户{index:02d}", "phone": f"13900001{index:03d}", "quantity": 2, "resource_customer_no": f"DEMO-{index:03d}", "age": 30 + index, "occupation": "演示职业"}], unit_price_cents=1000 if paid else 0)
            if approve and not paid:
                order = sales.approve_order(platform, order.id, approved=True, version=order.version, reason="演示开卡")
            return order

    def visit(index, when, *, complete=False, pending=False):
        order = sale(index, when)
        with patch("django.utils.timezone.now", return_value=when):
            customer = customers.register_verified_customer(f"13900001{index:03d}")
            card = order.cards.order_by("serial").first()
            benefit = customers.claim(customer.id, card.id)
            appt = appointments.book(customer.id, benefit_id=benefit.id, clinic_id=clinic.id, requested_at=when + timedelta(hours=2))
            if not pending:
                appt = appointments.confirm(clinic_actor, appt.id, scheduled_at=when + timedelta(hours=2), version=appt.version)
        if complete:
            with patch("django.utils.timezone.now", return_value=when + timedelta(hours=3)):
                appointments.redeem(clinic_actor, appt.id, credential=card.credential, confirmed=True, version=appt.version)
        return appt

    visit(1, start + timedelta(days=2), complete=True)
    with patch("django.utils.timezone.now", return_value=instant(prior_month)):
        bill = finance.generate_clinic_bill(clinic.id, issued_on=prior_month)
        proof = asset(clinic_actor, "payment")
        receipt = finance.submit_receipt(clinic_actor, bill.id, amount_cents=bill.total_cents, paid_at=timezone.now(), payer="演示门诊（无真实资金）", reference="SYNTHETIC-RECEIPT-001", attachment_ids=[str(proof.id)], version=bill.version)
        finance.review_receipt(platform, receipt.id, approved=True, version=receipt.version, reason="合成收款事实，仅验收")
    visit(2, instant(prior_month + timedelta(days=10)), complete=True)
    with patch("django.utils.timezone.now", return_value=instant(current_month)):
        finance.generate_clinic_bill(clinic.id, issued_on=current_month)
        finance.generate_partner_bills(issued_on=current_month)
    visit(3, now, pending=True)
    visit(4, now)
    expired = visit(5, now - timedelta(hours=30))
    appointments.process_deadline(expired.id, now=now)
    automatic = visit(6, now - timedelta(hours=80))
    appointments.process_deadline(automatic.id, now=now)
    sale(7, now)
    sale(8, now, approve=False)
    sale(9, now, paid=True)
    sale(10, now, physical=True)
    audit(platform, org, "acceptance.seeded", fixture="v1", synthetic_only=True)
    return True


class Command(BaseCommand):
    help = "只在空的独立验收库生成合成资料；重复运行不重置数据"

    def handle(self, *args, **options):
        created = seed()
        self.stdout.write("验收合成资料已初始化" if created else "已初始化，保留现有操作和数据")
