import time

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from chihuitong.models import Card, CardRange, Outbox
from chihuitong.services import jobs, sales

from .support import api_client
from .test_sales import order_fixture, sales_setup


class BoundedCapacityTests(TestCase):
    def test_ten_thousand_physical_cards_atomic_issuance_and_bounded_page(self):
        sales_setup(self)
        order = order_fixture(self, physical=True, quantity=10000)
        started = time.monotonic()
        order = sales.request_approval(self.platform, order.id, approved=True, version=order.version,
                                      reason="合成容量验证", validity_days=180)
        self.assertEqual(order.status, "issuing")
        jobs.run_one()
        elapsed = time.monotonic() - started
        order.refresh_from_db()
        self.assertEqual(order.status, "issued")
        self.assertEqual(Card.objects.filter(order=order).count(), 10000)
        self.assertEqual(CardRange.objects.filter(order=order).count(), 1)
        self.assertEqual(Outbox.objects.get(kind="sales.issue").status, "done")
        client = api_client(self.resource)
        with CaptureQueriesContext(connection) as queries:
            response = client.get(f"/api/v1/sales-orders/{order.id}/cards", {"page_size": 20})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data["results"]), 20)
        self.assertEqual(response.data["total"], 10000)
        self.assertLess(len(queries), 100)
        # Report observed time; this is not an SLA or proof of unlimited load.
        print(f"CAPACITY_SAMPLE cards=10000 seconds={elapsed:.3f} page_queries={len(queries)}")
