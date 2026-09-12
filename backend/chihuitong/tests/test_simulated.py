from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase, override_settings

from chihuitong.acceptance import AcceptanceSMS
from chihuitong.errors import BusinessError
from chihuitong.integrations.simulated import SimulatedWeChatPay
from chihuitong.models import PaymentAttempt, ReceiptLedger
from chihuitong.services import payments

from . import test_finance


@override_settings(
    ACCEPTANCE_ENABLED=True,
    ACCEPTANCE_SIMULATED_EXTERNALS=True,
    WECHAT_PAY_ENABLED=False,
    ENVIRONMENT="test",
)
class SimulationTests(TestCase):
    setUp = test_finance.FinanceTests.setUp

    def test_virtual_payment_uses_real_ledger_idempotency_and_never_network(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")):
            result = payments.create_payment(
                self.clinic_actor,
                self.bill.id,
                version=self.bill.version,
                method="native",
                key="synthetic-payment-key",
            )
            duplicate = payments.create_payment(
                self.clinic_actor,
                self.bill.id,
                version=self.bill.version,
                method="native",
                key="synthetic-payment-key",
            )
            payments.reconcile(result.id)
        self.assertEqual(result.id, duplicate.id)
        self.assertEqual(result.status, "success")
        self.assertTrue(payments.projection(result)["simulated"])
        self.assertEqual(PaymentAttempt.objects.count(), 1)
        ledger = ReceiptLedger.objects.get()
        self.assertEqual(ledger.kind, "wechat_simulated")
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.status, "settled")
        self.assertEqual(self.bill.received_cents, self.bill.total_cents)

    def test_simulation_never_allowed_in_production_or_live_payment(self):
        for config in [
            {"ENVIRONMENT": "production"},
            {"ACCEPTANCE_ENABLED": False},
            {"ACCEPTANCE_SIMULATED_EXTERNALS": False},
            {"WECHAT_PAY_ENABLED": True},
        ]:
            with override_settings(**config), self.assertRaises(BusinessError):
                SimulatedWeChatPay()
            with override_settings(**config), self.assertRaises(BusinessError):
                AcceptanceSMS().send_template("13800000004", None, {}, context="test")

    def test_sms_has_explicit_synthetic_reference_and_no_public_payment_callback(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")):
            reference = AcceptanceSMS().send_template(
                "13800000004", SimpleNamespace(code="appointment.new"), {}, context="attempt-id"
            )
        self.assertEqual(reference, "SIMULATED-attempt-id")
        with self.assertRaises(BusinessError):
            SimulatedWeChatPay().notification({}, b"{}")
