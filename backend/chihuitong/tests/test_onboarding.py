from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from chihuitong.errors import BusinessError
from chihuitong.models import Clinic, ClinicAgreement, ClinicCooperation
from chihuitong.services import clinics, cooperations, files, onboarding

from .support import api_client
from .test_catalog import CatalogTests, image_bytes


@override_settings(
    ACCEPTANCE_ENABLED=True,
    ACCEPTANCE_SIMULATED_EXTERNALS=True,
    ENVIRONMENT="test",
    WECHAT_PAY_ENABLED=False,
)
class OnboardingTests(TestCase):
    def setUp(self):
        CatalogTests.setUp(self)
        self.asset = files.upload_file(
            self.channel, data=image_bytes(), filename="合成签署合同.png", purpose="contract"
        )
        now = timezone.now()
        self.data = {
            "number": "JOINT-SYNTH-01",
            "starts_at": now - timedelta(days=1),
            "ends_at": now + timedelta(days=365),
            "contact": {"name": "合成联系人", "phone": "13900000005"},
            "clinic_ids": [],
            "product_ids": [str(self.product.id)],
            "attachment_ids": [str(self.asset.id)],
            "payment_mode": "instant",
            "settlement_cycle": "",
        }
        self.subject = {
            "name": "合成测试法定主体",
            "kind": "single",
            "credit_code": "91110000123456789A",
            "admin_name": "合成管理员",
            "admin_phone": "13900000095",
        }
        self.clinic_data = {
            "profile": self.profile,
            "channel_id": self.channel.organization.id,
            "admin_name": "合成前台管理",
            "admin_phone": "13900000096",
        }

    def apply(self):
        return onboarding.submit(
            self.channel, clinic=self.clinic_data, agreement=self.data, subject=self.subject
        )

    def signed(self, item):
        stamp = timezone.now().isoformat()
        return cooperations.record_paper(
            self.platform,
            item.id,
            version=item.version,
            data={
                "received_at": stamp,
                "platform_signed_at": stamp,
                "signed_attachment_ids": [str(self.asset.id)],
            },
        )

    def test_joint_final_is_atomic_and_standalone_reviews_blocked(self):
        item = self.apply()
        clinic = item.onboarding_change.clinic
        self.assertEqual(item.status, "pending")
        self.assertEqual(clinic.profile_version, 0)
        with self.assertRaises(BusinessError):
            clinics.review_profile(
                self.platform,
                item.onboarding_change_id,
                approved=True,
                version=item.onboarding_change.version,
                reason="不能单独审核",
            )
        with self.assertRaises(BusinessError):
            cooperations.review_agreement(
                self.platform,
                item.id,
                approved=True,
                version=item.version,
                reason="不能单独审核",
                final=True,
            )
        with self.assertRaises(BusinessError):
            onboarding.review(
                self.platform,
                item.id,
                version=item.version,
                approved=True,
                reason="缺原件",
                final=True,
            )
        clinic.refresh_from_db()
        self.assertEqual(clinic.profile_version, 0)
        self.assertNotEqual(clinic.service_status, "online")
        item = self.signed(item)
        onboarding.review(
            self.platform,
            item.id,
            version=item.version,
            approved=True,
            reason="合同资料齐全",
            final=True,
        )
        clinic.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(
            (clinic.review_status, clinic.service_status, item.status),
            ("approved", "online", "approved"),
        )
        self.assertEqual(clinic.products.filter(status="online").count(), 1)
        with self.assertRaises(BusinessError):
            onboarding.review(
                self.platform,
                item.id,
                version=item.version,
                approved=True,
                reason="重复审核",
                final=True,
            )

    def test_precheck_rejection_and_resubmission_reuses_subject_and_store(self):
        item = self.apply()
        item = onboarding.review(
            self.platform,
            item.id,
            version=item.version,
            approved=True,
            reason="内容预审",
            final=False,
        )
        self.assertEqual(item.status, "pending")
        item = onboarding.review(
            self.platform,
            item.id,
            version=item.version,
            approved=False,
            reason="补充资料",
            final=False,
        )
        clinic = Clinic.objects.get(pk=item.onboarding_change.clinic_id)
        new = onboarding.submit(
            self.channel,
            clinic=self.clinic_data,
            agreement=self.data,
            clinic_id=clinic.id,
            version=clinic.version,
        )
        self.assertEqual(new.cooperation_id, item.cooperation_id)
        self.assertEqual(new.onboarding_change.clinic_id, clinic.id)
        self.assertEqual(ClinicCooperation.objects.count(), 1)
        item.refresh_from_db()
        self.assertEqual(item.status, "rejected")

    def test_empty_chain_draft_and_credit_code_uniqueness(self):
        data = {**self.data, "payment_mode": "postpaid", "settlement_cycle": "monthly"}
        item = cooperations.start_agreement(
            self.channel, subject={**self.subject, "kind": "chain"}, data=data
        )
        self.assertEqual(item.coverage.count(), 0)
        with self.assertRaises(BusinessError):
            cooperations.start_agreement(
                self.channel, subject={**self.subject, "kind": "chain"}, data=data
            )
        item = cooperations.submit_agreement(self.channel, item.id, version=item.version)
        item = self.signed(item)
        with self.assertRaises(BusinessError):
            cooperations.review_agreement(
                self.platform,
                item.id,
                version=item.version,
                approved=True,
                reason="无覆盖不得生效",
                final=True,
            )
        self.assertEqual(ClinicAgreement.objects.count(), 1)

    def test_failed_first_submission_does_not_leave_subject_or_account(self):
        with self.assertRaises(BusinessError):
            onboarding.submit(
                self.channel,
                clinic={**self.clinic_data, "profile": {}},
                agreement=self.data,
                subject=self.subject,
            )
        self.assertEqual(ClinicCooperation.objects.count(), 0)
        self.assertEqual(ClinicAgreement.objects.count(), 0)

    def test_contract_list_role_isolation_and_single_submission_idempotency(self):
        client = api_client(self.channel)
        body = {"clinic": self.clinic_data, "subject": self.subject, "agreement": self.data}
        first = client.post(
            "/api/v1/clinic-onboarding",
            body,
            format="json",
            HTTP_IDEMPOTENCY_KEY="joint-synthetic-idempotency",
        )
        self.assertEqual(first.status_code, 409, first.data)
        again = client.post(
            "/api/v1/clinic-onboarding",
            body,
            format="json",
            HTTP_IDEMPOTENCY_KEY="joint-synthetic-idempotency",
        )
        self.assertEqual(again.status_code, 409)
        record = self.apply()
        self.assertEqual(ClinicCooperation.objects.count(), 1)
        other = api_client(self.other).get("/api/v1/contracts?kind=clinic")
        self.assertEqual(other.data["total"], 0)
        self.assertEqual(
            api_client(self.other).get("/api/v1/clinic-agreements/" + str(record.id)).status_code,
            404,
        )
