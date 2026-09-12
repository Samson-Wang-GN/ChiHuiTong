import tempfile
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from chihuitong.acceptance import ACCOUNTS, GateMiddleware, inbox, mailbox_path
from chihuitong.errors import BusinessError
from chihuitong.identity import request_code, verify_code
from chihuitong.management.commands.seed_acceptance import seed
from chihuitong.models import Appointment, ClinicBill, LoginChallenge, Membership, Organization, PartnerBill
from chihuitong.services.common import Actor

from .support import actor_fixture, api_client


class AcceptanceTests(TestCase):
    def setUp(self):
        self.storage = tempfile.TemporaryDirectory()
        self.addCleanup(self.storage.cleanup)
        self.config = override_settings(ACCEPTANCE_ENABLED=True, ACCEPTANCE_PROXY_TOKEN="x" * 48, ENVIRONMENT="test", PRIVATE_STORAGE=Path(self.storage.name), SMS_BACKEND="chihuitong.acceptance.AcceptanceSMS")
        self.config.enable()
        self.addCleanup(self.config.disable)

    def test_gate_rejects_direct_and_cross_origin_requests(self):
        gate = GateMiddleware(lambda request: HttpResponse("ok"))
        factory = RequestFactory()
        self.assertEqual(gate(factory.get("/")).status_code, 403)
        self.assertEqual(gate(factory.get("/", HTTP_X_CHT_ACCEPTANCE="wrong")).status_code, 403)
        self.assertEqual(gate(factory.get("/", HTTP_X_CHT_ACCEPTANCE="x" * 48)).status_code, 200)
        self.assertEqual(gate(factory.post("/", HTTP_X_CHT_ACCEPTANCE="x" * 48, HTTP_ORIGIN="https://evil.invalid")).status_code, 403)
        with override_settings(ENVIRONMENT="production"):
            self.assertEqual(gate(factory.get("/", HTTP_X_CHT_ACCEPTANCE="x" * 48)).status_code, 403)

    def test_inbox_is_encrypted_random_expiring_and_consumed(self):
        phone = ACCOUNTS["platform"][0]
        actor_fixture(phone=phone)
        request_code(phone, "acceptance-test")
        request = RequestFactory().post("/acceptance/sms", data={"phone": phone}, content_type="application/json")
        response = inbox(request)
        self.assertEqual(response.status_code, 200)
        code = response.data["code"]
        self.assertEqual(len(code), 6)
        self.assertNotIn(code, mailbox_path(phone).read_text())
        with self.assertRaises(BusinessError):
            request_code(phone, "acceptance-test")
        self.assertIn("token", verify_code(phone, code, "acceptance-test"))
        self.assertEqual(inbox(request).status_code, 404)
        with self.assertRaises(BusinessError):
            verify_code(phone, code, "acceptance-test")
        with patch("django.utils.timezone.now", return_value=timezone.now()+timedelta(seconds=61)):
            request_code(phone, "acceptance-test")
        LoginChallenge.objects.update(expires_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(inbox(request).status_code, 404)

    def test_unlisted_and_production_sms_are_blocked(self):
        with self.assertRaises(BusinessError):
            request_code("13800000099", "acceptance-test")
        with override_settings(ENVIRONMENT="production"):
            with self.assertRaises(BusinessError):
                request_code(ACCOUNTS["platform"][0], "acceptance-test")

    def test_seed_persists_scoped_scenarios_and_never_resets(self):
        guard = SimpleNamespace(ACCEPTANCE_ENABLED=True, ENVIRONMENT="test", DATABASES={"default":{"NAME":"chihuitong_acceptance_fixture"}})
        with patch("chihuitong.management.commands.seed_acceptance.settings", guard):
            self.assertTrue(seed())
            before = Appointment.objects.count()
            self.assertFalse(seed())
            self.assertEqual(Appointment.objects.count(), before)
        self.assertEqual(Membership.objects.count(), 4)
        self.assertEqual(ClinicBill.objects.count(), 2)
        self.assertEqual(PartnerBill.objects.count(), 2)
        for kind in ["platform", "broker", "channel", "clinic"]:
            actor = Actor(Membership.objects.select_related("organization", "account").get(organization__kind=kind))
            client = api_client(actor)
            self.assertEqual(client.get("/api/v1/workbench").status_code, 403)
            client.defaults["HTTP_X_CHT_ACCEPTANCE"] = "x" * 48
            self.assertEqual(client.get("/api/v1/workbench").status_code, 200)
            result = client.get("/api/v1/appointments")
            self.assertEqual(result.status_code, 200)
            self.assertGreater(result.data["total"], 0)
            if kind != "platform":
                self.assertEqual(client.get("/api/v1/organizations").status_code, 403)
        self.assertEqual(Organization.objects.count(), 4)
