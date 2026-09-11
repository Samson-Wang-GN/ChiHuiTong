from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from django.utils import timezone

from chihuitong.models import PaymentAttempt, ReceiptLedger
from chihuitong.services import payments

from . import test_finance


class PaymentConcurrencyTests(TransactionTestCase):
    setUp = test_finance.FinanceTests.setUp

    def gateway(self):
        return SimpleNamespace(config=SimpleNamespace(mchid="1900000001", appid="wxSYNTHETIC00001"))

    def test_inflight_creation_reuses_attempt_without_holding_bill_lock(self):
        gateway = self.gateway()
        entered, release = Event(), Event()
        calls = []

        def create(attempt, openid=None):
            calls.append(attempt.id)
            self.assertFalse(connection.in_atomic_block)
            entered.set()
            self.assertTrue(release.wait(timeout=10))
            return {"code_url": "weixin://wxpay/synthetic"}

        gateway.create = create

        def run(key):
            close_old_connections()
            try:
                return payments.create_payment(
                    self.clinic_actor,
                    self.bill.id,
                    version=self.bill.version,
                    method="native",
                    key=key,
                )
            finally:
                close_old_connections()

        with patch("chihuitong.services.payments.WeChatPay", return_value=gateway):
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(run, "parallel-first")
                self.assertTrue(entered.wait(timeout=10))
                try:
                    second = pool.submit(run, "parallel-second").result(timeout=10)
                    self.assertEqual(second.status, "creating")
                finally:
                    release.set()
                final = first.result(timeout=10)
                self.assertEqual(final.id, second.id)
        self.assertEqual(len(calls), 1)
        self.assertEqual(PaymentAttempt.objects.count(), 1)

    def test_parallel_observation_books_money_once(self):
        gateway = self.gateway()
        gateway.create = lambda attempt, openid=None: {"code_url": "weixin://wxpay/synthetic"}
        with patch("chihuitong.services.payments.WeChatPay", return_value=gateway):
            attempt = payments.create_payment(
                self.clinic_actor,
                self.bill.id,
                version=self.bill.version,
                method="native",
                key="parallel-observe",
            )
        data = {
            "appid": attempt.appid,
            "mchid": attempt.mchid,
            "out_trade_no": attempt.number,
            "trade_state": "SUCCESS",
            "trade_type": "NATIVE",
            "transaction_id": "SYNTHETIC-CONCURRENT-001",
            "amount": {"total": attempt.amount_cents, "currency": "CNY"},
            "success_time": timezone.now().isoformat(),
        }

        def run():
            close_old_connections()
            try:
                return payments.observe(attempt.id, data).status
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: run(), range(4)))
        self.assertEqual(results, ["success"] * 4)
        self.assertEqual(ReceiptLedger.objects.count(), 1)
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.received_cents, attempt.amount_cents)
