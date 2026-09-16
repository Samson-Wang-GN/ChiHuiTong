import io
import json
from pathlib import Path

from django.test import TestCase, override_settings
from pypdf import PdfReader

from chihuitong.errors import BusinessError
from chihuitong.models import ClinicCooperation, ContractPreparation, ContractTemplate
from chihuitong.services import contract_preparation as service, files
from .support import actor_fixture, api_client
from .test_onboarding import OnboardingTests


@override_settings(ACCEPTANCE_ENABLED=True, ACCEPTANCE_SIMULATED_EXTERNALS=True, ENVIRONMENT="test", WECHAT_PAY_ENABLED=False)
class PreparationTests(TestCase):
    def setUp(self):
        OnboardingTests.setUp(self)
        self.payload = json.loads(json.dumps({"clinic": self.clinic_data, "subject": self.subject, "agreement": self.data}, default=str))
        self.payload["agreement"]["attachment_ids"] = []

    def template(self):
        return service.template(self.platform, kind="single", title="合成合同测试样张（禁止实际签署）",
            body="合同编号：{{number}}\n甲方：{{platform_name}}\n乙方：{{subject_name}}\n期限：{{starts_at}}至{{ends_at}}\n产品：{{products}}\n门店：{{stores}}\n付款方式：{{payment_mode}}\n" +
            ("本段为自动测试的中文排版内容，不构成真实合同条款。\n" * 55) + "甲方签字/盖章：____________\n乙方签字/盖章：____________",
            platform_name="合成平台主体", platform_credit_code="91110000123456789B", confirmed=True)

    def draft(self):
        return service.save(self.channel, kind="single", payload=self.payload)

    def test_partial_draft_missing_template_and_scope(self):
        item = service.save(self.channel, kind="single", payload={})
        self.assertEqual(item.status, "draft")
        self.assertEqual(ClinicCooperation.objects.count(), 0)
        with self.assertRaises(BusinessError) as err:
            service.generate(self.channel, item.id, version=item.version)
        self.assertEqual(err.exception.code, "template_missing")
        other = actor_fixture("channel", "13900000801")
        self.assertFalse(service.visible(other).exists())
        staff = actor_fixture("channel", "13900000802", role="staff", org=self.channel.organization)
        self.assertFalse(service.visible(staff).exists())
        with self.assertRaises(BusinessError):
            service.get(other, item.id)
        self.assertEqual(api_client(self.channel).get("/api/v1/contract-templates").status_code, 403)
        self.assertEqual(api_client(self.platform).get("/api/v1/contracts?kind=legacy").status_code, 400)

    def test_generate_sign_submit_atomic_idempotent_and_pdf(self):
        self.template()
        item = self.draft()
        item = service.generate(self.channel, item.id, version=item.version)
        first = item.prints.get(revision=1)
        raw = files.file_bytes(first.asset)
        reader = PdfReader(io.BytesIO(raw))
        self.assertGreaterEqual(len(reader.pages), 2)
        content = "".join(page.extract_text() for page in reader.pages)
        self.assertIn("合成平台主体", content)
        self.assertIn(self.subject["name"], content)
        self.assertNotIn("{{", content)
        self.assertTrue(files.can_read_file(self.channel, first.asset))
        Path("contract-test-sample.pdf").write_bytes(raw)
        again = service.generate(self.channel, item.id, version=item.version)
        self.assertEqual(again.generation, 1)
        with self.assertRaises(BusinessError):
            service.submit(self.channel, item.id, version=item.version)
        with self.assertRaises(BusinessError):
            service.sign(self.channel, item.id, version=item.version, generation=1, attachment_ids=[str(first.asset_id)])
        item = service.sign(self.channel, item.id, version=item.version, generation=1, attachment_ids=[str(self.asset.id)])
        client = api_client(self.channel)
        data = {"version": item.version}
        url = f"/api/v1/contract-preparations/{item.id}/submit"
        one = client.post(url, data, format="json", HTTP_IDEMPOTENCY_KEY="prepare-submit-once")
        self.assertEqual(one.status_code, 200, one.data)
        two = client.post(url, data, format="json", HTTP_IDEMPOTENCY_KEY="prepare-submit-once")
        self.assertEqual(one.data["agreement_id"], two.data["agreement_id"])
        self.assertEqual(ClinicCooperation.objects.count(), 1)

    def test_changed_contract_requires_new_signature_and_new_template_keeps_old_print(self):
        old = self.template()
        item = self.draft()
        item = service.generate(self.channel, item.id, version=item.version)
        item = service.sign(self.channel, item.id, version=item.version, generation=1, attachment_ids=[str(self.asset.id)])
        self.template()
        old.refresh_from_db()
        self.assertEqual(old.status, "retired")
        service.current_print(self.channel, item)
        self.payload["subject"]["name"] = "更新的合成主体"
        item = service.save(self.channel, kind="single", payload=self.payload, pk=item.id, version=item.version)
        self.assertEqual(item.signed_generation, 0)
        with self.assertRaises(BusinessError):
            service.submit(self.channel, item.id, version=item.version)
        item = service.generate(self.channel, item.id, version=item.version)
        self.assertEqual(item.generation, 2)
        self.assertEqual(item.prints.count(), 2)

    def test_draft_api_retries_and_template_validation(self):
        client = api_client(self.channel)
        for _ in range(2):
            response = client.post("/api/v1/contract-preparations", {"kind": "single", "payload": {}}, format="json", HTTP_IDEMPOTENCY_KEY="empty-draft-once")
            self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(ContractPreparation.objects.count(), 1)
        response = api_client(self.platform).post("/api/v1/contract-templates", {
            "kind": "single", "title": "合成", "body": "{{unknown}}", "platform_name": "合成", "platform_credit_code": "91110000123456789B", "confirmed": True,
        }, format="json", HTTP_IDEMPOTENCY_KEY="bad-template-test")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(ContractTemplate.objects.count(), 0)
