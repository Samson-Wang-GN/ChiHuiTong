from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from chihuitong.crypto import digest
from chihuitong.errors import BusinessError
from chihuitong.models import Customer, ImportBatch, Outbox
from chihuitong.services import files, imports

from .support import actor_fixture, api_client
from .test_sales import xlsx_bytes


def asset_for(actor, rows=None):
    return files.upload_file(
        actor,
        data=xlsx_bytes(rows or [["姓名", "手机号", "数量"], ["合成客户", "13900000555", 1]]),
        filename="synthetic.xlsx",
        purpose="sales_excel",
    )


def mapping_for(batch):
    return {
        "version": batch.version,
        "sheet": "客户表",
        "header_row": 1,
        "mapping": {"name": 0, "phone": 1, "quantity": 2},
        "quantity_mode": "column",
    }


class SyncImportTests(TestCase):
    def setUp(self):
        self.actor = actor_fixture("broker", "13900000002")
        self.client = api_client(self.actor)

    def test_sync_api_and_lost_response_retry_do_not_duplicate(self):
        asset = asset_for(self.actor)
        payload = {"asset_id": str(asset.id)}
        first = self.client.post(
            "/api/v1/imports", payload, format="json", HTTP_IDEMPOTENCY_KEY="sync-create-test"
        )
        again = self.client.post(
            "/api/v1/imports", payload, format="json", HTTP_IDEMPOTENCY_KEY="sync-create-test"
        )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(first.json(), again.json())
        self.assertEqual(first.json()["status"], "mapping")
        batch = ImportBatch.objects.get()
        url = f"/api/v1/imports/{batch.id}/mapping"
        payload = mapping_for(batch)
        first = self.client.post(
            url, payload, format="json", HTTP_IDEMPOTENCY_KEY="sync-mapping-test"
        )
        again = self.client.post(
            url, payload, format="json", HTTP_IDEMPOTENCY_KEY="sync-mapping-test"
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json(), again.json())
        self.assertEqual(first.json()["status"], "validated")
        self.assertEqual(batch.rows.count(), 1)
        self.assertFalse(Outbox.objects.exists())
        self.assertFalse(Customer.objects.exists())
        stale = self.client.post(
            url, payload, format="json", HTTP_IDEMPOTENCY_KEY="sync-mapping-stale"
        )
        self.assertEqual(stale.status_code, 409)
        other = api_client(actor_fixture("insurance", "13900000003"))
        self.assertEqual(
            other.post(
                url, payload, format="json", HTTP_IDEMPOTENCY_KEY="sync-other-scope"
            ).status_code,
            404,
        )

    def test_file_failure_rolls_back_creation_and_same_request_can_retry(self):
        asset = asset_for(self.actor)
        with patch(
            "chihuitong.services.imports.open_book",
            side_effect=BusinessError("invalid_excel", "合成错误", 400),
        ):
            response = self.client.post(
                "/api/v1/imports",
                {"asset_id": str(asset.id)},
                format="json",
                HTTP_IDEMPOTENCY_KEY="sync-file-retry",
            )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ImportBatch.objects.exists())
        response = self.client.post(
            "/api/v1/imports",
            {"asset_id": str(asset.id)},
            format="json",
            HTTP_IDEMPOTENCY_KEY="sync-file-retry",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "mapping")

    def test_validation_failure_preserves_previous_rows_and_version(self):
        batch = imports.create_import(self.actor, asset_for(self.actor).id)
        batch = imports.configure_import(self.actor, batch.id, **mapping_for(batch))
        version = batch.version
        row_ids = list(batch.rows.values_list("id", flat=True))
        with patch(
            "chihuitong.services.imports.open_book",
            side_effect=BusinessError("invalid_excel", "合成错误", 400),
        ):
            with self.assertRaises(BusinessError):
                imports.configure_import(self.actor, batch.id, **mapping_for(batch))
        batch.refresh_from_db()
        self.assertEqual((batch.status, batch.version), ("validated", version))
        self.assertEqual(list(batch.rows.values_list("id", flat=True)), row_ids)

    def test_bounded_matching_preserves_platform_name_conflict_and_duplicate_rules(self):
        # Customer identity is shared across resource providers, not scoped to uploader.
        Customer.objects.create(
            phone="13910000000", phone_index=digest("13910000000", purpose="phone"), name="已有姓名"
        )
        rows = [["姓名", "手机号", "数量"]] + [
            [f"合成{i}", str(13910000000 + i), 1] for i in range(1001)
        ]
        rows.append(["合成1", "13910000001", 1])
        batch = imports.create_import(self.actor, asset_for(self.actor, rows).id)
        with CaptureQueriesContext(connection) as captured:
            batch = imports.configure_import(self.actor, batch.id, **mapping_for(batch))
        lookups = [q for q in captured.captured_queries if 'FROM "chihuitong_customer"' in q["sql"]]
        self.assertEqual(len(lookups), 3)
        self.assertEqual((batch.status, batch.error_rows), ("validated", 3))
        self.assertEqual(batch.rows.get(row_number=2).errors[0]["code"], "customer_conflict")
        self.assertEqual(Customer.objects.get().name, "已有姓名")


class ConcurrentSyncImportTests(TransactionTestCase):
    def test_concurrent_same_key_creates_only_one_completed_batch(self):
        actor = actor_fixture("broker", "13900000002")
        asset = asset_for(actor)
        credentials = api_client(actor)._credentials

        def submit(_):
            close_old_connections()
            try:
                client = APIClient()
                client.credentials(**credentials)
                response = client.post(
                    "/api/v1/imports",
                    {"asset_id": str(asset.id)},
                    format="json",
                    HTTP_IDEMPOTENCY_KEY="sync-concurrent-test",
                )
                return response.status_code, response.json()
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, range(2)))
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0][0], 201)
        self.assertEqual(ImportBatch.objects.count(), 1)
        self.assertEqual(ImportBatch.objects.get().status, "mapping")
        self.assertFalse(Outbox.objects.exists())
