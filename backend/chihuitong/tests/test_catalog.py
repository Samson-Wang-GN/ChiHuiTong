import io
import uuid
from datetime import timedelta

from django.db import DatabaseError, transaction
from django.test import TestCase
from django.utils import timezone
from PIL import Image
from pypdf import PdfWriter

from chihuitong.errors import BusinessError
from chihuitong.models import (
    AuditEvent,
    Contract,
    ContractVersion,
    Membership,
    ProductRevision,
)
from chihuitong.services import catalog, clinics, contracts, files
from chihuitong.services.common import Actor

from .support import actor_fixture, api_client


def image_bytes():
    output = io.BytesIO()
    Image.new("RGB", (100, 60), color="white").save(output, "PNG")
    return output.getvalue()


def product_fixture(platform, **changes):
    data = {
        "internal_name": f"合成产品{uuid.uuid4().hex[:8]}",
        "external_name": "口腔洁治体验",
        "product_type": "service",
        "usage_rules": "请提前预约，单次使用1份",
        "redemption_units": 1,
        "fee_cents": 6000,
        "validity_days": 180,
        "status": "active",
    }
    data.update(changes)
    return catalog.save_product(platform, data)


def contract_fixture(
    platform,
    owner,
    *,
    product=None,
    split="20",
    start=None,
    end=None,
    cycle="monthly",
    submitter=None,
):
    actor = submitter or platform
    asset = files.upload_file(
        actor, data=image_bytes(), filename="合成合同.png", purpose="contract"
    )
    data = {
        "starts_at": start or timezone.now() - timedelta(days=1),
        "ends_at": end or timezone.now() + timedelta(days=365),
        "settlement_cycle": cycle,
        "contact": {"name": "合成联系人", "phone": "13900000999"},
        "attachment_ids": [str(asset.id)],
    }
    master = Contract.objects.filter(organization=owner).first()
    item = contracts.create_version(
        actor,
        owner.id,
        number=master.number if master else f"HT-{uuid.uuid4().hex[:10]}",
        data=data,
    )
    if product:
        contracts.save_term(
            platform, item.id, product_id=product.id, mode="percent", value=split, reason="合成测试"
        )
    item = contracts.submit_version(actor, item.id, version=item.version)
    return contracts.review_version(
        platform, item.id, approved=True, version=item.version, reason="合成测试通过"
    )


class CatalogTests(TestCase):
    def setUp(self):
        self.platform = actor_fixture()
        self.channel = actor_fixture("channel", "13900000002")
        self.resource = actor_fixture("broker", "13900000003")
        self.other = actor_fixture("channel", "13900000004")
        self.product = product_fixture(self.platform)
        self.channel_contract = contract_fixture(
            self.platform, self.channel.organization, product=self.product
        )
        self.resource_contract = contract_fixture(
            self.platform, self.resource.organization, product=self.product
        )
        license_asset = files.upload_file(
            self.channel, data=image_bytes(), filename="合成资质.png", purpose="license"
        )
        self.profile = {
            "name": "合成测试门诊",
            "legal_entity": "合成经营主体",
            "province": "北京市",
            "city": "北京市",
            "district": "海淀区",
            "address": "合成测试路1号",
            "business_hours": "09:00-18:00",
            "frontdesk_phone": "13900000088",
            "business_contact": "合成业务联系人",
            "business_phone": "010-12345678",
            "business_license_ids": [str(license_asset.id)],
            "medical_license_ids": [str(license_asset.id)],
            "cover_id": None,
            "responsible_id": str(self.channel.membership.id),
            "location": {"status": "unconfirmed"},
        }
        self.clinic = clinics.create_clinic(
            self.channel,
            channel_id=self.channel.organization.id,
            profile=self.profile,
            admin_name="合成门诊管理",
            admin_phone="13900000005",
        )
        self.clinic_actor = Actor(
            Membership.objects.select_related("organization", "account").get(
                organization=self.clinic.organization
            )
        )

    def approve_clinic(self):
        self.clinic.refresh_from_db()
        change = clinics.submit_profile(
            self.channel, self.clinic.id, profile=self.profile, version=self.clinic.version
        )
        clinics.review_profile(
            self.platform, change.id, approved=True, version=change.version, reason="资料合成审核"
        )
        self.clinic.refresh_from_db()
        return self.clinic

    def test_product_revision_and_decimal_split(self):
        self.assertEqual(catalog.cents("1.005"), 101)
        self.assertEqual(contracts.split_cents(1, "percent", "50"), 1)
        with self.assertRaises(BusinessError):
            catalog.cents(1.005)
        with self.assertRaises(BusinessError):
            contracts.save_term(
                self.platform,
                self.resource_contract.id,
                product_id=self.product.id,
                mode="percent",
                value="90",
                version=1,
                reason="超额",
            )
        original = ProductRevision.objects.get(product=self.product).snapshot
        data = {key: value for key, value in original.items() if key not in {"id", "version"}}
        data["internal_name"] = "新版内部名称"
        catalog.save_product(
            self.platform, data, product_id=self.product.id, version=1, reason="调整"
        )
        self.assertNotEqual(original["internal_name"], "新版内部名称")
        self.assertEqual(ProductRevision.objects.filter(product=self.product).count(), 2)

    def test_source_brand_isolation_and_platform_only_edit(self):
        brand = catalog.save_brand(
            self.platform, self.resource.organization.id, name="客户保险福利"
        )
        response = api_client(self.resource).get(
            f"/api/v1/organizations/{self.resource.organization.id}/source-brands"
        )
        self.assertEqual(response.json()["results"][0]["id"], str(brand.id))
        self.assertEqual(
            api_client(self.channel)
            .get(f"/api/v1/organizations/{self.resource.organization.id}/source-brands")
            .status_code,
            404,
        )
        with self.assertRaises(BusinessError):
            catalog.save_brand(self.resource, self.resource.organization.id, name="越权")

    def test_profile_rejection_preserves_effective_version_and_pending_duplicate(self):
        self.approve_clinic()
        modified = {**self.profile, "business_contact": "新的合成联系人"}
        change = clinics.submit_profile(
            self.clinic_actor, self.clinic.id, profile=modified, version=self.clinic.version
        )
        self.clinic.refresh_from_db()
        self.assertEqual(self.clinic.profile["business_contact"], self.profile["business_contact"])
        with self.assertRaises(BusinessError):
            clinics.submit_profile(
                self.channel, self.clinic.id, profile=modified, version=self.clinic.version
            )
        clinics.review_profile(
            self.platform, change.id, approved=False, version=change.version, reason="资料需核实"
        )
        self.clinic.refresh_from_db()
        self.assertEqual(self.clinic.profile_version, 1)
        self.assertEqual(self.clinic.profile["business_contact"], self.profile["business_contact"])
        with self.assertRaises(BusinessError):
            clinics.review_profile(
                self.platform, change.id, approved=True, version=change.version, reason="重复审核"
            )

    def test_missing_contact_and_forbidden_timeout(self):
        with self.assertRaises(BusinessError):
            clinics.submit_profile(
                self.channel,
                self.clinic.id,
                profile={**self.profile, "business_contact": ""},
                version=self.clinic.version,
            )
        for actor in [self.channel, self.clinic_actor]:
            with self.assertRaises(BusinessError):
                clinics.set_confirmation_hours(
                    actor, self.clinic.id, hours=48, version=self.clinic.version, reason="越权"
                )
        with self.assertRaises(BusinessError):
            clinics.submit_profile(
                self.channel,
                self.clinic.id,
                profile={**self.profile, "confirmation_hours": 48},
                version=self.clinic.version,
            )

    def test_channel_and_staff_data_scope(self):
        staff = actor_fixture("channel", "13900000006", "staff", self.channel.organization)
        for actor in [staff, self.other, self.resource]:
            self.assertEqual(clinics.visible_clinics(actor).count(), 0)
            with self.assertRaises(BusinessError):
                clinics.get_clinic(actor, self.clinic.id)
        self.assertEqual(clinics.visible_clinics(self.channel).count(), 1)

    def test_location_confirmation_address_binding_and_private_projection(self):
        address = "".join(self.profile[k] for k in ["province", "city", "district", "address"])
        location = {
            "status": "confirmed",
            "longitude": "116.3",
            "latitude": "40.0",
            "coordinate_system": "GCJ-02",
            "address_snapshot": address,
            "source": "map_manual",
            "confirmed": True,
        }
        data, _ = clinics.validate_profile(
            self.channel, {**self.profile, "location": location}, self.channel.organization
        )
        self.assertEqual(data["location"]["confirmed_by"], str(self.channel.membership.id))
        with self.assertRaises(BusinessError):
            clinics.validate_profile(
                self.channel,
                {**self.profile, "address": "新的地址", "location": location},
                self.channel.organization,
            )
        with self.assertRaises(BusinessError):
            clinics.validate_profile(
                self.channel,
                {**self.profile, "location": {**location, "longitude": "NaN"}},
                self.channel.organization,
            )

    def test_tripartite_contract_platform_review_only_and_expired_renewal(self):
        self.approve_clinic()
        item = contract_fixture(
            self.platform, self.clinic.organization, submitter=self.channel, cycle="weekly"
        )
        self.assertEqual(item.channel_id, self.channel.organization.id)
        with self.assertRaises(BusinessError):
            contracts.review_version(
                self.channel, item.id, approved=True, version=item.version, reason="越权"
            )
        ContractVersion.objects.filter(pk=item.id).update(
            starts_at=timezone.now() - timedelta(days=30),
            ends_at=timezone.now() - timedelta(days=1),
        )
        renewed = contract_fixture(self.platform, self.clinic.organization, submitter=self.channel)
        self.assertEqual(renewed.revision, 2)
        self.assertEqual(contracts.current_contract(self.clinic.organization.id).id, renewed.id)

    def test_current_contract_does_not_use_future_and_stock_uses_recent_expired(self):
        future = contract_fixture(
            self.platform,
            self.resource.organization,
            product=self.product,
            start=timezone.now() + timedelta(days=30),
            end=timezone.now() + timedelta(days=400),
        )
        self.assertNotEqual(
            contracts.current_contract(
                self.resource.organization.id, product_id=self.product.id
            ).id,
            future.id,
        )
        ContractVersion.objects.filter(pk=self.resource_contract.id).update(
            starts_at=timezone.now() - timedelta(days=10),
            ends_at=timezone.now() - timedelta(days=1),
        )
        with self.assertRaises(BusinessError):
            contracts.current_contract(self.resource.organization.id)
        self.assertEqual(
            contracts.current_contract(
                self.resource.organization.id, product_id=self.product.id, stock=True
            ).id,
            self.resource_contract.id,
        )

    def test_new_business_and_online_product_no_credit_conditions(self):
        with self.assertRaises(BusinessError):
            clinics.set_service_status(
                self.platform,
                self.clinic.id,
                status="online",
                version=self.clinic.version,
                reason="尚未审核",
            )
        self.approve_clinic()
        contract_fixture(self.platform, self.clinic.organization, submitter=self.channel)
        link = clinics.set_clinic_product(
            self.channel, self.clinic.id, product_id=self.product.id, online=True, reason="启用"
        )
        self.assertEqual(link.status, "online")
        clinics.set_service_status(
            self.platform,
            self.clinic.id,
            status="online",
            version=self.clinic.version,
            reason="开始服务",
        )
        self.clinic.refresh_from_db()
        self.assertEqual(self.clinic.service_status, "online")
        fees = contracts.resolve_fees(self.resource.organization.id, self.clinic, self.product)
        self.assertEqual(
            (
                fees["fee_cents"],
                fees["resource_cents"],
                fees["channel_cents"],
                fees["platform_cents"],
            ),
            (6000, 1200, 1200, 3600),
        )

    def test_channel_change_requires_offline_and_new_tripartite(self):
        self.approve_clinic()
        contract_fixture(self.platform, self.clinic.organization, submitter=self.channel)
        contract_fixture(self.platform, self.other.organization, product=self.product)
        clinics.set_service_status(
            self.platform,
            self.clinic.id,
            status="online",
            version=self.clinic.version,
            reason="上线",
        )
        self.clinic.refresh_from_db()
        with self.assertRaises(BusinessError):
            clinics.change_channel(
                self.platform,
                self.clinic.id,
                channel_id=self.other.organization.id,
                responsible_id=self.other.membership.id,
                version=self.clinic.version,
                reason="变更",
            )
        clinics.set_service_status(
            self.platform,
            self.clinic.id,
            status="offline",
            version=self.clinic.version,
            reason="先下线",
        )
        self.clinic.refresh_from_db()
        clinics.change_channel(
            self.platform,
            self.clinic.id,
            channel_id=self.other.organization.id,
            responsible_id=self.other.membership.id,
            version=self.clinic.version,
            reason="新渠道",
        )
        self.clinic.refresh_from_db()
        self.assertEqual(clinics.visible_clinics(self.channel).count(), 0)
        with self.assertRaises(BusinessError):
            clinics.assert_new_business(self.clinic)

    def test_files_isolated_reencoded_and_linked_for_review(self):
        asset = files.upload_file(
            self.channel, data=image_bytes(), filename="cover.png", purpose="cover"
        )
        data = files.file_bytes(asset)
        self.assertTrue(data.startswith(b"\xff\xd8"))
        with self.assertRaises(BusinessError):
            files.download_file(self.other, asset.id)
        self.assertEqual(files.download_file(self.platform, asset.id)[0].id, asset.id)
        self.profile["cover_id"] = str(asset.id)
        self.approve_clinic()
        self.assertEqual(files.download_file(self.clinic_actor, asset.id)[0].id, asset.id)

    def test_invalid_files_and_active_pdf_blocked(self):
        with self.assertRaises(BusinessError):
            files.upload_file(
                self.channel, data=b"not an image", filename="fake.png", purpose="cover"
            )
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        output = io.BytesIO()
        writer.write(output)
        asset = files.upload_file(
            self.channel, data=output.getvalue(), filename="static.pdf", purpose="contract"
        )
        self.assertEqual(asset.content_type, "application/pdf")
        writer.add_js("app.alert('blocked')")
        output = io.BytesIO()
        writer.write(output)
        with self.assertRaises(BusinessError):
            files.upload_file(
                self.channel, data=output.getvalue(), filename="active.pdf", purpose="contract"
            )

    def test_audit_is_append_only_in_database(self):
        record = AuditEvent.objects.first()
        with self.assertRaises(DatabaseError), transaction.atomic():
            AuditEvent.objects.filter(pk=record.pk).update(action="tampered")
        with self.assertRaises(DatabaseError), transaction.atomic():
            AuditEvent.objects.filter(pk=record.pk).delete()

    def test_authorized_product_list_defaults_offline_without_leaking_partner_split(self):
        response = api_client(self.channel).get(f"/api/v1/clinics/{self.clinic.id}/products")
        self.assertEqual(response.status_code, 200)
        row = response.json()["results"][0]
        self.assertEqual(row["status"], "offline")
        self.assertNotIn("value", row)
        self.assertNotIn("mode", row)
        employee = actor_fixture("clinic", "13900000007", "staff", self.clinic.organization)
        self.assertEqual(
            api_client(employee)
            .get(f"/api/v1/organizations/{self.clinic.organization.id}/contracts")
            .status_code,
            403,
        )
        self.assertEqual(
            api_client(employee).get(f"/api/v1/clinics/{self.clinic.id}").status_code, 403
        )
