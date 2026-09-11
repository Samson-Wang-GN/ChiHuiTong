import io
from datetime import datetime, timedelta
from unittest.mock import patch

from django.db import DatabaseError, transaction
from django.test import TestCase
from django.utils import timezone
from openpyxl import load_workbook

from chihuitong.models import DomainEvent
from chihuitong.services import appointments, customers, metrics, sales

from .support import api_client
from .test_appointments import appointment_setup, confirmed_appointment
from .test_sales import approve, order_fixture


class MetricsTests(TestCase):
    def setUp(self):
        self.start = timezone.make_aware(datetime(2026, 7, 30, 10))
        with patch("django.utils.timezone.now", return_value=self.start):
            appointment_setup(self)
            self.appointment = confirmed_appointment(self)
        self.finish = self.start + timedelta(days=5)

    def cohort(self, actor=None, **kwargs):
        return metrics.Cohort(actor or self.resource, date_from=self.start.date(), date_to=self.start.date(), **kwargs)

    def test_multi_source_global_people_dedup_and_staff_order_scope(self):
        with patch("django.utils.timezone.now", return_value=self.start + timedelta(minutes=5)):
            second = approve(self, order_fixture(self, actor=self.other, brand=self.other_brand))
            customers.claim(self.customer.id, second.cards.first().id)
        result = self.cohort().summary()
        self.assertEqual((result["customers"], result["purchased"], result["activated"], result["appointments"]), (1, 2, 1, 1))
        self.assertEqual(result["activation_rate"], {"value": "50.0", "numerator": 1, "denominator": 2, "unit": "%"})
        self.assertEqual(self.cohort(self.platform).summary()["customers"], 1)
        self.assertEqual(self.cohort(self.platform).summary()["purchased"], 4)
        self.assertEqual(self.cohort(self.staff).summary()["purchased"], 0)
        self.assertIsNone(self.cohort(self.staff).summary()["activation_rate"]["value"])

    def test_reversal_is_historical_not_current_and_negative_net(self):
        with patch("django.utils.timezone.now", return_value=self.scheduled + timedelta(hours=1)):
            record = appointments.redeem(self.clinic_actor, self.appointment.id, credential=self.card.credential, confirmed=True, version=self.appointment.version)
        reversed_at = self.scheduled + timedelta(days=1)
        with patch("django.utils.timezone.now", return_value=reversed_at):
            appointments.reverse_redemption(self.clinic_actor, record.id, version=record.version, reason="合成错误核销")
        cohort = self.cohort(as_of=self.finish)
        self.assertEqual(cohort.summary(at=self.scheduled + timedelta(hours=2))["redemptions"], 1)
        self.assertEqual(cohort.summary()["redemptions"], 0)
        points = cohort.trend(metric="redemptions", date_from=self.start.date(), date_to=reversed_at.date(), granularity="day", display="net")["points"]
        self.assertEqual([point["value"] for point in points], [0, 1, -1])
        historic = self.cohort(as_of=self.scheduled + timedelta(hours=2))
        kind, qs = historic.details("redemptions")
        self.assertEqual(kind, "redemption")
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.get().snapshot_status, "active")

    def test_stop_deducts_cards_not_customer_and_frozen_activation_retained(self):
        with patch("django.utils.timezone.now", return_value=self.start + timedelta(hours=2)):
            pending = sales.request_stop(self.resource, self.order.id, action="stop", version=self.order.version, reason="停止未领取")
            sales.review_stop(self.platform, self.order.id, approved=True, version=pending.version, reason="核验停止")
            sales.freeze_card(self.platform, self.card.id, frozen=True, reason="冻结测试")
        result = self.cohort().summary()
        self.assertEqual((result["customers"], result["purchased"], result["voided"], result["activated"]), (1, 1, 1, 1))
        kind, denominator = self.cohort().details("activation_rate", component="denominator")
        self.assertEqual((kind, denominator.count()), ("card", 1))

    def test_physical_customer_binding_only_after_activation(self):
        with patch("django.utils.timezone.now", return_value=self.start + timedelta(hours=1)):
            order = approve(self, order_fixture(self, physical=True, quantity=3))
        before = self.start + timedelta(hours=2)
        with patch("django.utils.timezone.now", return_value=self.start + timedelta(days=1)):
            customers.activate(self.customer.id, order.cards.first().credential)
        cohort = self.cohort(mode="physical")
        self.assertEqual(cohort.summary(at=before)["customers"], 0)
        self.assertEqual(cohort.summary()["customers"], 1)
        self.assertEqual(cohort.summary()["activated"], 1)
        self.assertEqual(cohort.summary()["activation_rate"]["value"], "33.3")

    def test_month_week_boundaries_ratios_not_averaged_and_system_completion(self):
        with patch("django.utils.timezone.now", return_value=self.scheduled + timedelta(hours=73)):
            appointments.process_deadline(self.appointment.id)
        cohort = self.cohort(as_of=self.finish)
        result = cohort.summary()
        self.assertEqual((result["appointments"], result["redemptions"]), (1, 0))
        points = cohort.trend(metric="appointment_rate", date_from=self.start.date(), date_to=self.finish.date(), granularity="month")["points"]
        self.assertEqual(points[0]["to"], "2026-07-31")
        self.assertEqual(points[1]["from"], "2026-08-01")
        self.assertEqual(points[1]["value"]["numerator"], 1)
        weeks = cohort.trend(metric="purchased", date_from=self.start.date(), date_to=self.finish.date(), granularity="week")["points"]
        self.assertEqual(weeks[0]["to"], "2026-08-02")
        self.assertEqual(weeks[1]["from"], "2026-08-03")
        _, query = cohort.details("appointments")
        self.assertEqual(query.get().snapshot_completion, "system")

    def test_api_filters_details_full_export_and_role_isolation(self):
        params = {"date_from": "2026-07-30", "date_to": "2026-07-30", "metric": "purchased", "page_size": 1}
        client = api_client(self.resource)
        response = client.get("/api/v1/customer-overview", params)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data["resources"]), 1)
        listing = client.get("/api/v1/customer-overview/details", params)
        self.assertEqual(listing.status_code, 200, listing.data)
        self.assertEqual(listing.data["total"], 2)
        self.assertEqual(len(listing.data["results"]), 1)
        exported = client.get("/api/v1/customer-overview/export.xlsx", params)
        self.assertEqual(exported.status_code, 200)
        book = load_workbook(io.BytesIO(exported.content), read_only=True)
        self.assertEqual(len(list(book.active.values)), 3)
        book.close()
        people = client.get("/api/v1/customer-overview/details", {**params, "metric": "customers"})
        self.assertEqual(people.data["total"], 1)
        self.assertEqual(people.data["results"][0]["phone"], self.customer.phone)
        cards = client.get("/api/v1/customer-overview/customer-cards", {**params, "customer_id": str(self.customer.id)})
        self.assertEqual(cards.data["total"], 2)
        self.assertEqual(client.get("/api/v1/customer-overview", {**params, "resource_id": str(self.other.organization.id)}).status_code, 403)
        self.assertEqual(api_client(self.channel).get("/api/v1/customer-overview", params).status_code, 403)
        self.assertEqual(client.get("/api/v1/customer-overview", {**params, "forged": True}).status_code, 400)
        product_response = client.get("/api/v1/customer-overview/products", params)
        self.assertEqual(product_response.status_code, 200, product_response.data)
        self.assertEqual(product_response.data["results"][0]["purchased"], 2)

    def test_event_ledger_append_only(self):
        event = DomainEvent.objects.first()
        with self.assertRaises(DatabaseError), transaction.atomic():
            DomainEvent.objects.filter(pk=event.pk).update(kind="voided")
        with self.assertRaises(DatabaseError), transaction.atomic():
            DomainEvent.objects.filter(pk=event.pk).delete()
