"""Real mini API contracts; only WeChat identity verification is substituted."""
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings

from chihuitong.services import appointments

from .test_appointments import appointment_setup, confirmed_appointment
from .test_mini import MINI_SETTINGS, mini_client
from .test_finance import FinanceTests
from .support import actor_fixture


@override_settings(MINI_PROGRAMS=MINI_SETTINGS)
class NativeApiTests(TestCase):
    def setUp(self):
        appointment_setup(self)

    def post(self, client, path, data):
        result = client.post(path, data, format="json", HTTP_IDEMPOTENCY_KEY=uuid.uuid4().hex)
        self.assertIn(result.status_code, (200, 201), result.data)
        return result.data

    def test_booking_reschedule_scan_quote_redeem_and_reverse_through_native_endpoints(self):
        customer, _ = mini_client("customer", self.customer.phone)
        clinic, _ = mini_client("clinic", self.clinic_actor.account.phone)
        cbase, mbase = "/api/v1/mini/customer", "/api/v1/mini/clinic"
        booked = self.post(customer, cbase + "/appointments", {
            "benefit_id": str(self.benefit.id), "clinic_id": str(self.clinic.id),
            "requested_at": self.scheduled.isoformat(),
        })
        key = booked["id"]
        confirmed = self.post(clinic, mbase + f"/appointments/{key}/confirm", {
            "version": booked["version"], "scheduled_at": self.scheduled.isoformat(),
        })
        later = self.scheduled + timedelta(hours=1)
        self.post(customer, cbase + f"/appointments/{key}/reschedule", {
            "version": confirmed["version"], "proposed_at": later.isoformat(),
        })
        pending = customer.get(cbase + f"/appointments/{key}").data
        self.assertIsNone(pending["redemption_qr"])
        self.assertEqual(pending["scheduled_at"], self.scheduled.isoformat())
        change = clinic.get(mbase + f"/appointments/{key}").data["reschedules"][0]
        self.post(clinic, mbase + f"/reschedules/{change['id']}/review", {
            "version": change["version"], "approved": True, "reason": "已协商",
        })
        with patch("django.utils.timezone.now", return_value=later + timedelta(minutes=10)):
            clinic, _ = mini_client("clinic", self.clinic_actor.account.phone)
            candidate = self.post(clinic, mbase + "/redemptions/scan", {
                "credential": self.card.credential,
            })["results"][0]
            self.assertEqual(candidate["id"], key)
            quote = self.post(clinic, mbase + "/redemptions/quote", {
                "credential": self.card.credential, "appointment_id": key,
            })
            self.post(clinic, mbase + "/redemptions", {
                "credential": self.card.credential, "appointment_id": key,
                "version": quote["version"], "quote": quote["quote"], "confirmed": True,
            })
            detail = clinic.get(mbase + f"/appointments/{key}").data
            self.assertEqual(detail["status"], "completed")
            transaction = detail["redemptions"][0]
            self.assertFalse(transaction["clinic_settled"])
            self.post(clinic, mbase + f"/redemptions/{transaction['id']}/reverse", {
                "version": transaction["version"], "reason": "合成错误核销撤销",
            })
            self.assertEqual(clinic.get(mbase + f"/appointments/{key}").data["status"], "success")

    def test_customer_absence_projection_and_feedback_are_actionable(self):
        item = confirmed_appointment(self)
        with patch("django.utils.timezone.now", return_value=self.scheduled + timedelta(hours=1)):
            appointments.report_absent(self.clinic_actor, item.id, version=item.version, confirmed=True)
            customer, _ = mini_client("customer", self.customer.phone)
            path = f"/api/v1/mini/customer/appointments/{item.id}"
            data = customer.get(path).data
            self.assertTrue(data["reserved"])
            self.assertIsNotNone(data["clinic_absent_at"])
            self.assertIsNone(data["redemption_qr"])
            self.assertIsNotNone(data["expires_at"])
            restored = self.post(customer, path + "/feedback", {
                "version": data["version"], "arrived": False, "confirmed": True,
            })
            self.assertFalse(restored["reserved"])

    def test_qr_blocks_conflict_restoration_and_expired_appointment_date(self):
        item = confirmed_appointment(self)
        customer, _ = mini_client("customer", self.customer.phone)
        path = f"/api/v1/mini/customer/appointments/{item.id}"
        for field in ("conflict", "restoration_pending"):
            setattr(item, field, True)
            item.save(update_fields=[field])
            self.assertIsNone(customer.get(path).data["redemption_qr"])
            setattr(item, field, False)
            item.save(update_fields=[field])
        item.scheduled_at = self.benefit.expires_at + timedelta(days=1)
        item.save(update_fields=["scheduled_at"])
        self.assertIsNone(customer.get(path).data["redemption_qr"])

    def test_qr_uses_appointment_date_not_late_scan_date(self):
        item = confirmed_appointment(self)
        with patch("django.utils.timezone.now", return_value=self.benefit.expires_at + timedelta(days=1)):
            customer, _ = mini_client("customer", self.customer.phone)
            detail = customer.get(f"/api/v1/mini/customer/appointments/{item.id}")
            self.assertEqual(detail.data["redemption_qr"], self.card.credential)

    def test_clinic_contract_and_product_links_use_distinct_clinic_id(self):
        self.assertNotEqual(self.clinic.id, self.clinic_actor.organization.id)
        clinic, _ = mini_client("clinic", self.clinic_actor.account.phone)
        response = clinic.get(f"/api/v1/mini/clinic/organizations/{self.clinic_actor.organization.id}/cooperation")
        self.assertEqual(response.status_code, 200)
        products = clinic.get(response.data["products_endpoint"])
        self.assertEqual(products.status_code, 200, products.data)
        self.assertEqual(products.data["results"][0]["external_name"], self.product.external_name)
        for state in ["draft", "pending", "effective", "not_started", "expired", "superseded", "rejected", "terminated"]:
            self.assertEqual(clinic.get(response.data["history_endpoint"], {"status": state}).status_code, 200)


@override_settings(MINI_PROGRAMS=MINI_SETTINGS)
class NativeBillTests(TestCase):
    setUp = FinanceTests.setUp

    def test_payment_history_export_and_receipt_are_admin_only(self):
        admin, _ = mini_client("clinic", self.clinic_actor.account.phone)
        employee = actor_fixture("clinic", "13900000779", "staff", self.clinic_actor.organization)
        staff, _ = mini_client("clinic", employee.account.phone)
        base = f"/api/v1/mini/clinic/bills/{self.bill.id}"
        for suffix in ("/payments", "/export.xlsx", "/receipts", "/lines"):
            self.assertEqual(admin.get(base + suffix).status_code, 200, suffix)
            self.assertEqual(staff.get(base + suffix).status_code, 403, suffix)
        result = admin.post(base + "/payments", {}, format="json")
        self.assertEqual(result.status_code, 405)
        self.assertEqual(admin.get(base + "/lines?status=active").status_code, 200)
        self.assertEqual(admin.get(base + "/lines?status=disabled").status_code, 200)
