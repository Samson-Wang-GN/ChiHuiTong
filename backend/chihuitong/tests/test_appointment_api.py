from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase

from chihuitong.models import ContractProduct, Redemption
from chihuitong.services import appointments

from .support import actor_fixture, api_client
from .test_appointments import appointment_setup, confirmed_appointment


class AppointmentAPITests(TestCase):
    def setUp(self):
        appointment_setup(self)

    def test_reminder_snapshot_full_without_patient_identifiers(self):
        item = appointments.book(
            self.customer.id,
            benefit_id=self.benefit.id,
            clinic_id=self.clinic.id,
            requested_at=self.scheduled,
        )
        client = api_client(self.clinic_actor)
        result = client.get("/api/v1/appointments/reminder-snapshot")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["count"], 1)
        self.assertNotIn(self.customer.phone, str(result.data))
        before = result.data["revision"]
        confirmed = client.post(
            f"/api/v1/appointments/{item.id}/confirm",
            {
                "version": item.version,
                "scheduled_at": self.scheduled.isoformat(),
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="confirm-first",
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        after = client.get("/api/v1/appointments/reminder-snapshot")
        self.assertEqual(after.data["count"], 0)
        self.assertNotEqual(before, after.data["revision"])
        self.assertEqual(
            api_client(self.channel).get("/api/v1/appointments/reminder-snapshot").status_code, 403
        )

    def test_other_clinic_and_channel_cannot_process(self):
        item = confirmed_appointment(self)
        other = actor_fixture("clinic", "13900000081")
        for actor in [other, self.channel, self.resource, self.platform]:
            response = api_client(actor).post(
                f"/api/v1/appointments/{item.id}/cancel",
                {
                    "version": item.version,
                    "reason": "越权不可取消",
                },
                format="json",
                HTTP_IDEMPOTENCY_KEY="unauthorized-cancel",
            )
            self.assertIn(response.status_code, [403, 404])
        data = api_client(self.clinic_actor).get(f"/api/v1/appointments/{item.id}").data
        self.assertEqual(data["phone"], self.customer.phone)
        self.assertEqual(data["settlement_status"], "not_charged")
        self.assertNotIn("credential", data)

    def test_scan_quote_redeem_reverse_and_forged_quote(self):
        item = confirmed_appointment(self)
        with patch("django.utils.timezone.now", return_value=self.scheduled + timedelta(hours=1)):
            client = api_client(self.clinic_actor)
            response = client.post(
                "/api/v1/redemptions/scan", {"credential": self.card.credential}, format="json"
            )
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(len(response.data["results"]), 1)
            quote = client.post(
                "/api/v1/redemptions/quote",
                {
                    "credential": self.card.credential,
                    "appointment_id": str(item.id),
                },
                format="json",
            )
            self.assertEqual(quote.status_code, 200, quote.data)
            self.assertEqual(quote.data["fee_cents"], 6000)
            body = {
                "credential": self.card.credential,
                "appointment_id": str(item.id),
                "version": item.version,
                "confirmed": True,
                "quote": quote.data["quote"] + "tamper",
            }
            invalid = client.post(
                "/api/v1/redemptions", body, format="json", HTTP_IDEMPOTENCY_KEY="bad-quote"
            )
            self.assertEqual(invalid.status_code, 409, invalid.data)
            self.assertEqual(Redemption.objects.count(), 0)
            body["quote"] = quote.data["quote"]
            success = client.post(
                "/api/v1/redemptions", body, format="json", HTTP_IDEMPOTENCY_KEY="good-quote"
            )
            self.assertEqual(success.status_code, 200, success.data)
            again = client.post(
                "/api/v1/redemptions", body, format="json", HTTP_IDEMPOTENCY_KEY="good-quote"
            )
            self.assertEqual(again.data, success.data)
            self.assertEqual(Redemption.objects.count(), 1)
            reversed_result = client.post(
                f"/api/v1/redemptions/{success.data['id']}/reverse",
                {
                    "version": success.data["version"],
                    "reason": "合成错误核销",
                },
                format="json",
                HTTP_IDEMPOTENCY_KEY="reverse-first",
            )
            self.assertEqual(reversed_result.status_code, 200, reversed_result.data)
            item.refresh_from_db()
            self.assertEqual(item.status, "success")

    def test_disabled_terms_allow_stock_redemption_and_changed_quote_blocks(self):
        item = confirmed_appointment(self)
        with patch("django.utils.timezone.now", return_value=self.scheduled + timedelta(hours=1)):
            quote = appointments.redemption_quote(
                self.clinic_actor, item.id, credential=self.card.credential
            )
            ContractProduct.objects.filter(product=self.product).update(status="disabled")
            from chihuitong.errors import BusinessError

            with self.assertRaisesMessage(BusinessError, "条款已变化"):
                appointments.redeem(
                    self.clinic_actor,
                    item.id,
                    credential=self.card.credential,
                    confirmed=True,
                    version=item.version,
                    quote=quote["quote"],
                )
            fresh = appointments.redemption_quote(
                self.clinic_actor, item.id, credential=self.card.credential
            )
            record = appointments.redeem(
                self.clinic_actor,
                item.id,
                credential=self.card.credential,
                confirmed=True,
                version=item.version,
                quote=fresh["quote"],
            )
            self.assertEqual(record.fee_cents, 6000)
