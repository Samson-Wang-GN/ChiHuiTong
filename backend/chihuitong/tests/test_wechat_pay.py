import base64
import io
import json
import re
import time
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from chihuitong.errors import BusinessError
from chihuitong.integrations.wechat_pay import (
    PayConfiguration,
    WeChatPay,
    json_object,
    load_configuration,
)
from chihuitong.models import Outbox, PaymentAttempt, PaymentNotification, ReceiptLedger
from chihuitong.services import jobs, payments

from . import test_finance
from .support import actor_fixture, api_client


def crypto_fixture():
    merchant = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    wechat = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    config = PayConfiguration(
        "1900000001",
        "wxSYNTHETIC00001",
        "AABBCC",
        merchant,
        "PUB_KEY_ID_100001",
        {"PUB_KEY_ID_100001": wechat.public_key()},
        b"0" * 32,
        "https://example.invalid/api/v1/payments/wechat/notify",
    )
    return config, wechat


def signed_headers(key, raw, *, timestamp=None):
    stamp = str(timestamp if timestamp is not None else int(time.time()))
    nonce = "synthetic-nonce"
    signature = key.sign(
        f"{stamp}\n{nonce}\n".encode() + raw + b"\n", padding.PKCS1v15(), hashes.SHA256()
    )
    return {
        "Wechatpay-Timestamp": stamp,
        "Wechatpay-Nonce": nonce,
        "Wechatpay-Serial": "PUB_KEY_ID_100001",
        "Wechatpay-Signature": base64.b64encode(signature).decode(),
    }


def encrypted_notification(config, key, data, notification_id="SYNTHETIC-NOTICE-001"):
    nonce, aad = b"012345678901", b"transaction"
    encrypted = AESGCM(config.api_v3_key).encrypt(nonce, json.dumps(data).encode(), aad)
    raw = json.dumps(
        {
            "id": notification_id,
            "event_type": "TRANSACTION.SUCCESS",
            "resource_type": "encrypt-resource",
            "resource": {
                "algorithm": "AEAD_AES_256_GCM",
                "original_type": "transaction",
                "nonce": nonce.decode(),
                "associated_data": aad.decode(),
                "ciphertext": base64.b64encode(encrypted).decode(),
            },
        }
    ).encode()
    return raw, signed_headers(key, raw)


class CryptoTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config, cls.wx_key = crypto_fixture()

    def test_authorization_canonical_bytes_and_client_signature(self):
        gateway = WeChatPay(self.config)
        raw = '{"description":"合成中文"}'.encode()
        auth = gateway.authorization(
            "POST", "/v3/pay/transactions/native", raw, timestamp=123, nonce="nonce"
        )
        signature = re.search(r'signature="([^"]+)"', auth).group(1)
        self.config.private_key.public_key().verify(
            base64.b64decode(signature),
            b"POST\n/v3/pay/transactions/native\n123\nnonce\n" + raw + b"\n",
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        params = gateway.client_parameters("synthetic-prepay")
        message = f"{self.config.appid}\n{params['timeStamp']}\n{params['nonceStr']}\n{params['package']}\n".encode()
        self.config.private_key.public_key().verify(
            base64.b64decode(params["paySign"]), message, padding.PKCS1v15(), hashes.SHA256()
        )

    def test_signature_raw_bytes_expiry_unknown_key_and_probe_rejected(self):
        gateway = WeChatPay(self.config)
        body = b'{"safe":true}'
        headers = signed_headers(self.wx_key, body)
        gateway.verify(headers, body)
        for bad_headers, bad_body in [
            (headers, body + b" "),
            (signed_headers(self.wx_key, body, timestamp=int(time.time()) - 301), body),
            ({**headers, "Wechatpay-Serial": "PUB_KEY_ID_999"}, body),
            ({**headers, "Wechatpay-Signature": "WECHATPAY/SIGNTEST/invalid"}, body),
        ]:
            with self.assertRaises(BusinessError):
                gateway.verify(bad_headers, bad_body)

    def test_notification_decryption_wrong_key_and_duplicate_json(self):
        gateway = WeChatPay(self.config)
        data = {"out_trade_no": "synthetic", "amount": {"total": 1}}
        raw, headers = encrypted_notification(self.config, self.wx_key, data)
        self.assertEqual(gateway.notification(headers, raw)[1], data)
        wrong = WeChatPay(replace(self.config, api_v3_key=b"1" * 32))
        with self.assertRaises(BusinessError):
            wrong.notification(headers, raw)
        for body in [b'{"a":1,"a":2}', b"[]", b"not json"]:
            with self.assertRaises(BusinessError):
                json_object(body)

    def test_http_response_verification_and_no_unsigned_success(self):
        gateway = WeChatPay(self.config)
        raw = b'{"code_url":"weixin://wxpay/synthetic"}'

        class Response(io.BytesIO):
            headers = signed_headers(self.wx_key, raw)

        with patch("urllib.request.OpenerDirector.open", return_value=Response(raw)) as call:
            result = gateway.request("POST", "/v3/pay/transactions/native", {"synthetic": True})
            self.assertIn("code_url", result)
            self.assertEqual(call.call_args.args[0].host, "api.mch.weixin.qq.com")
        with patch("urllib.request.OpenerDirector.open", return_value=Response(raw + b" ")):
            with self.assertRaises(BusinessError):
                gateway.request("POST", "/v3/pay/transactions/native", {})

    def test_missing_real_configuration_fails_closed(self):
        with self.assertRaises(BusinessError):
            load_configuration()


class PaymentTests(TestCase):
    setUp = test_finance.FinanceTests.setUp

    def gateway(self):
        gateway = SimpleNamespace(
            config=SimpleNamespace(mchid="1900000001", appid="wxSYNTHETIC00001")
        )
        gateway.create = lambda attempt, openid=None: {"code_url": "weixin://wxpay/synthetic"}
        return gateway

    def create(self, key="payment-first"):
        with patch("chihuitong.services.payments.WeChatPay", return_value=self.gateway()):
            return payments.create_payment(
                self.clinic_actor, self.bill.id, version=self.bill.version, method="native", key=key
            )

    def success(self, attempt):
        return {
            "appid": attempt.appid,
            "mchid": attempt.mchid,
            "out_trade_no": attempt.number,
            "amount": {"total": attempt.amount_cents, "currency": "CNY"},
            "trade_type": "NATIVE",
            "trade_state": "SUCCESS",
            "transaction_id": "SYNTHETIC-WX-001",
            "success_time": timezone.now().isoformat(),
        }

    def test_create_idempotent_and_unknown_never_releases_payment(self):
        attempt = self.create()
        self.assertEqual(attempt.status, "pending")
        self.assertEqual(self.create().id, attempt.id)
        self.assertEqual(self.create("another-key").id, attempt.id)
        self.assertEqual(PaymentAttempt.objects.count(), 1)
        self.assertEqual(Outbox.objects.filter(kind="payment.reconcile").count(), 1)
        from chihuitong.services import finance

        with self.assertRaises(BusinessError):
            finance.submit_receipt(
                self.clinic_actor,
                self.bill.id,
                amount_cents=self.bill.total_cents,
                paid_at=timezone.now(),
                payer="合成门诊",
                reference="SYNTHETIC-OFFLINE",
                attachment_ids=[str(self.proof.id)],
                version=self.bill.version,
            )

    def test_network_timeout_returns_unknown_with_same_order(self):
        gateway = self.gateway()

        def fail(*args, **kwargs):
            raise BusinessError("wechat_network_unknown", "合成超时", 503)

        gateway.create = fail
        with patch("chihuitong.services.payments.WeChatPay", return_value=gateway):
            attempt = payments.create_payment(
                self.clinic_actor,
                self.bill.id,
                version=self.bill.version,
                method="native",
                key="timeout-one",
            )
            self.assertEqual(attempt.status, "unknown")
            again = payments.create_payment(
                self.clinic_actor,
                self.bill.id,
                version=self.bill.version,
                method="native",
                key="timeout-two",
            )
            self.assertEqual(attempt.id, again.id)

    def test_retry_lost_creation_reuses_number_and_does_not_mark_paid(self):
        attempt = self.create()
        attempt.status, attempt.gateway_payload = "unknown", {}
        attempt.save(update_fields=["status", "gateway_payload"])
        with patch("chihuitong.services.payments.WeChatPay", return_value=self.gateway()):
            retried = payments.retry_preparation(self.clinic_actor, attempt.id)
        self.assertEqual(retried.number, attempt.number)
        self.assertEqual(retried.preparation_count, 2)
        self.assertEqual(retried.status, "pending")
        self.assertEqual(PaymentAttempt.objects.count(), 1)
        self.assertFalse(ReceiptLedger.objects.exists())
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.status, "open")
        with patch("chihuitong.services.payments.WeChatPay", return_value=self.gateway()):
            with self.assertRaises(BusinessError):
                payments.retry_preparation(self.clinic_actor, attempt.id)

    def test_retry_generation_and_success_dominate_delayed_create(self):
        attempt = self.create()
        attempt.status, attempt.gateway_payload = "unknown", {}
        attempt.save(update_fields=["status", "gateway_payload"])
        gateway = self.gateway()
        def create_after_success(item, openid=None):
            payments.observe(item.id, self.success(item))
            return {"code_url": "weixin://wxpay/late"}
        gateway.create = create_after_success
        with patch("chihuitong.services.payments.WeChatPay", return_value=gateway):
            result = payments.retry_preparation(self.clinic_actor, attempt.id)
        self.assertEqual(result.status, "success")
        self.assertEqual(result.gateway_payload, {})
        self.assertEqual(ReceiptLedger.objects.count(), 1)

    def test_nonfinancial_feedback_does_not_invalidate_inflight_payment(self):
        from chihuitong.services import finance
        attempt = self.create()
        feedback = finance.submit_feedback(self.clinic_actor, self.bill.id, partner=False,
                                           message="合成核对说明", version=self.bill.version)
        finance.respond_feedback(self.platform, feedback.id, response="合成回复", version=feedback.version)
        payments.observe(attempt.id, self.success(attempt))
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.status, "settled")
        self.assertEqual(ReceiptLedger.objects.get().anomaly, "")

    def test_verified_success_once_and_late_pending_cannot_downgrade(self):
        attempt = self.create()
        data = self.success(attempt)
        payments.observe(attempt.id, data)
        payments.observe(attempt.id, data)
        self.bill.refresh_from_db()
        self.assertEqual(
            (self.bill.status, self.bill.received_cents), ("settled", self.bill.total_cents)
        )
        self.assertEqual(ReceiptLedger.objects.count(), 1)
        result = payments.observe(attempt.id, {**data, "trade_state": "NOTPAY"})
        self.assertEqual(result.status, "success")

    def test_amount_identity_or_currency_tampering_rejected(self):
        attempt = self.create()
        data = self.success(attempt)
        for changes in [
            {"appid": "wrong"},
            {"mchid": "wrong"},
            {"out_trade_no": "wrong"},
            {"amount": {"total": 1, "currency": "CNY"}},
            {"amount": {"total": attempt.amount_cents, "currency": "USD"}},
        ]:
            with self.assertRaises(BusinessError):
                payments.observe(attempt.id, {**data, **changes})
        self.assertEqual(ReceiptLedger.objects.count(), 0)

    def test_signed_callback_durable_then_async_and_duplicate(self):
        attempt = self.create()
        config, wx_key = crypto_fixture()
        data = self.success(attempt)
        data["payer"] = {"openid": "should-not-be-persisted"}
        raw, headers = encrypted_notification(config, wx_key, data)
        gateway = WeChatPay(config)
        with patch("chihuitong.services.payments.WeChatPay", return_value=gateway):
            client = APIClient()
            response = client.post(
                "/api/v1/payments/wechat/notify",
                raw,
                content_type="application/json",
                **{
                    "HTTP_" + key.upper().replace("-", "_"): value for key, value in headers.items()
                },
            )
            self.assertEqual(response.status_code, 204)
            notice = PaymentNotification.objects.get()
            self.assertNotIn("payer", notice.payload)
            self.assertEqual(ReceiptLedger.objects.count(), 0)
            same = payments.capture_notification(headers, raw)
            self.assertEqual(same.id, notice.id)
            Outbox.objects.exclude(kind="payment.notification").update(
                available_at=timezone.now() + timedelta(days=1)
            )
            jobs.run_one()
            payments.process_notification(notice.id)
            payments.process_notification(notice.id)
        self.assertEqual(ReceiptLedger.objects.count(), 1)
        notice.refresh_from_db()
        self.assertEqual(notice.status, "done")

    def test_query_and_signed_close_not_local_expiry(self):
        attempt = self.create()
        data = {**self.success(attempt), "trade_state": "NOTPAY"}
        gateway = self.gateway()
        gateway.query = lambda number: data
        closed = []
        gateway.close = closed.append
        with patch("chihuitong.services.payments.WeChatPay", return_value=gateway):
            pending = payments.reconcile(attempt.id)
            self.assertEqual(pending.status, "pending")
            self.assertEqual(closed, [])
            result = payments.reconcile(attempt.id, close=True)
            self.assertEqual(result.status, "closed")
            self.assertEqual(closed, [attempt.number])

    def test_wrong_version_real_money_saved_as_anomaly_not_lost(self):
        attempt = self.create()
        self.bill.version += 1
        self.bill.save(update_fields=["version"])
        result = payments.observe(attempt.id, self.success(attempt))
        self.assertEqual(result.error_code, "bill_version_changed")
        self.assertEqual(ReceiptLedger.objects.get().amount_cents, attempt.amount_cents)
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.received_cents, 0)

    def test_employee_cannot_create_payment_api_and_unsigned_callback(self):
        employee = actor_fixture("clinic", "13900000091", "staff", self.clinic_actor.organization)
        response = api_client(employee).post(
            f"/api/v1/clinic-bills/{self.bill.id}/payments",
            {"version": self.bill.version, "method": "native"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="forbidden-payment",
        )
        self.assertEqual(response.status_code, 403)
        config, _ = crypto_fixture()
        with patch("chihuitong.services.payments.WeChatPay", return_value=WeChatPay(config)):
            invalid = APIClient().post("/api/v1/payments/wechat/notify", {}, format="json")
            self.assertEqual(invalid.status_code, 401)
        self.assertEqual(PaymentNotification.objects.count(), 0)
