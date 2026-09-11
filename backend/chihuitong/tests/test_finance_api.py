import io
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from openpyxl import load_workbook

from chihuitong.models import PartnerBill
from chihuitong.services import finance

from .support import actor_fixture, api_client
from .test_finance import FinanceTests


class FinanceAPITests(TestCase):
    setUp = FinanceTests.setUp
    pay_clinic = FinanceTests.pay_clinic

    def test_clinic_bill_status_details_download_and_contact_policy(self):
        for actor in [self.platform, self.clinic_actor, self.channel]:
            client = api_client(actor)
            response = client.get("/api/v1/clinic-bills")
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(response.data["counts"]["all"], 1)
            detail = client.get(f"/api/v1/clinic-bills/{self.bill.id}")
            self.assertEqual(detail.status_code, 200)
            self.assertEqual(len(detail.data["revisions"]), 1)
            lines = client.get(f"/api/v1/clinic-bills/{self.bill.id}/lines")
            row = lines.data["results"][0]["transaction"]
            self.assertFalse(row["clinic_settled"])
            expected = self.customer.phone if actor != self.channel else self.customer.phone[:3] + "****" + self.customer.phone[-4:]
            self.assertEqual(row["phone"], expected)
            if actor == self.channel:
                self.assertNotIn("resource_cents", row)
            export = client.get(f"/api/v1/clinic-bills/{self.bill.id}/export.xlsx")
            self.assertEqual(export.status_code, 200)
            book = load_workbook(io.BytesIO(export.content), read_only=True)
            rows = list(book.active.values)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[1][4], expected)
            book.close()
        employee = actor_fixture("clinic", "13900000073", "staff", self.clinic_actor.organization)
        for path in ["/api/v1/clinic-bills", f"/api/v1/clinic-bills/{self.bill.id}/lines", f"/api/v1/clinic-bills/{self.bill.id}/export.xlsx"]:
            self.assertIn(api_client(employee).get(path).status_code, [403, 404])
            self.assertIn(api_client(self.resource).get(path).status_code, [403, 404, 200] if path == "/api/v1/clinic-bills" else [403, 404])

    def test_receipt_api_idempotency_feedback_and_response(self):
        client = api_client(self.clinic_actor)
        body = {"version": self.bill.version, "message": "请核对合成交易"}
        path = f"/api/v1/clinic-bills/{self.bill.id}/feedback"
        response = client.post(path, body, format="json", HTTP_IDEMPOTENCY_KEY="feedback-one")
        self.assertEqual(response.status_code, 201, response.data)
        again = client.post(path, body, format="json", HTTP_IDEMPOTENCY_KEY="feedback-one")
        self.assertEqual(response.data, again.data)
        self.bill.refresh_from_db()
        self.assertTrue(self.bill.dispute)
        replied = api_client(self.platform).post(f"/api/v1/finance-feedback/{response.data['id']}/respond",
            {"version": response.data["version"], "response": "逐笔核对无误，请确认"}, format="json", HTTP_IDEMPOTENCY_KEY="reply-one")
        self.assertEqual(replied.status_code, 200, replied.data)
        self.bill.refresh_from_db()
        self.assertFalse(self.bill.dispute)
        with patch("django.utils.timezone.now", return_value=self.clock):
            proof = client.post(f"/api/v1/clinic-bills/{self.bill.id}/receipts", {
                "version": self.bill.version, "amount_cents": self.bill.total_cents,
                "paid_at": self.clock.isoformat(), "payer": "合成门诊", "reference": "API-SYNTHETIC-001",
                "attachment_ids": [str(self.proof.id)],
            }, format="json", HTTP_IDEMPOTENCY_KEY="receipt-one")
            self.assertEqual(proof.status_code, 201, proof.data)
            review = api_client(self.platform).post(f"/api/v1/clinic-receipts/{proof.data['id']}/review", {
                "version": proof.data["version"], "approved": True, "reason": "已核对实际到账",
            }, format="json", HTTP_IDEMPOTENCY_KEY="receipt-review-one")
            self.assertEqual(review.status_code, 200, review.data)
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.status, "settled")

    def test_partner_staff_only_own_lines_not_whole_bill(self):
        with patch("django.utils.timezone.now", return_value=self.clock):
            self.pay_clinic()
        future = (self.issue_date.replace(day=28) + timedelta(days=4)).replace(day=1)
        finance.generate_partner_bills(issued_on=future)
        bill = PartnerBill.objects.get(organization=self.resource.organization)
        client = api_client(self.staff)
        for suffix in ["", "/lines", "/export.xlsx"]:
            self.assertEqual(client.get(f"/api/v1/partner-bills/{bill.id}{suffix}").status_code, 403)
        self.assertEqual(client.get("/api/v1/partner-bills").status_code, 403)
        rows = client.get("/api/v1/settlement-details")
        self.assertEqual(rows.status_code, 200)
        self.assertNotIn("total_cents", rows.data)
        self.assertEqual(rows.data["total"], 0)
        admin = api_client(self.resource)
        detail = admin.get(f"/api/v1/partner-bills/{bill.id}/lines")
        self.assertEqual(detail.status_code, 200, detail.data)
        row = detail.data["results"][0]["transaction"]
        self.assertNotIn("platform_cents", row)
        self.assertNotIn("channel_cents", row)
        self.assertTrue(row["clinic_settled"])

    def test_non_object_json_rejected_without_server_error(self):
        client = api_client(self.clinic_actor)
        response = client.post(f"/api/v1/clinic-bills/{self.bill.id}/receipts", [["bad"]], format="json")
        self.assertEqual(response.status_code, 400)
