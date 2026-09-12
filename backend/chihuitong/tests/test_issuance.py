from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from chihuitong.errors import BusinessError
from chihuitong.models import Card, CardRange, Outbox
from chihuitong.services import files, imports, jobs, sales, scheduler

from .support import api_client
from .test_sales import order_fixture, sales_setup, xlsx_bytes


class IssuanceTests(TestCase):
    def setUp(self):
        sales_setup(self)
        self.order = order_fixture(self, physical=True, quantity=1001)

    def queue(self):
        self.order = sales.request_approval(
            self.platform,
            self.order.id,
            approved=True,
            version=self.order.version,
            reason="合成大批开卡审核",
            validity_days=365,
        )
        return Outbox.objects.get(kind="sales.issue")

    def test_large_review_returns_queue_and_worker_issues_unique_range_once(self):
        job = self.queue()
        self.assertEqual(self.order.status, "issuing")
        self.assertEqual(Card.objects.count(), 0)
        response = api_client(self.resource).get(f"/api/v1/sales-orders/{self.order.id}")
        self.assertEqual(response.data["processing"]["status"], "pending")
        jobs.run_one()
        self.order.refresh_from_db()
        job.refresh_from_db()
        self.assertEqual(
            (self.order.status, job.status, self.order.validity_days), ("issued", "done", 365)
        )
        self.assertEqual(Card.objects.filter(order=self.order).count(), 1001)
        number_range = CardRange.objects.get(order=self.order)
        self.assertEqual(number_range.last_number - number_range.first_number, 1000)
        sales.process_issuance(job.payload)
        self.assertEqual(Card.objects.filter(order=self.order).count(), 1001)

    def test_failure_after_first_chunk_rolls_back_all_cards_and_number_range(self):
        job = self.queue()
        original = Card.objects.bulk_create
        attempts = 0

        def fail_second(*args, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 2:
                raise BusinessError("synthetic_failure", "合成中途失败", 409)
            return original(*args, **kwargs)

        with patch("chihuitong.services.sales.Card.objects.bulk_create", side_effect=fail_second):
            jobs.run_one()
        self.order.refresh_from_db()
        job.refresh_from_db()
        self.assertEqual((self.order.status, job.status), ("issue_failed", "failed"))
        self.assertEqual(Card.objects.count(), 0)
        self.assertEqual(CardRange.objects.count(), 0)
        scheduler.retry_job(self.platform, job.id, reason="修复后重新核验开卡")
        jobs.run_one()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "issued")
        self.assertEqual(Card.objects.count(), 1001)

    def test_failed_order_can_be_cancelled_or_reviewed_without_resurrecting_old_job(self):
        job = self.queue()
        with patch(
            "chihuitong.services.sales.process_issuance",
            side_effect=BusinessError("synthetic_failure", "合成失败", 409),
        ):
            jobs.run_one()
        self.order.refresh_from_db()
        sales.request_approval(
            self.platform,
            self.order.id,
            approved=False,
            version=self.order.version,
            reason="审核不通过",
        )
        self.order.refresh_from_db()
        job.refresh_from_db()
        self.assertEqual((self.order.status, job.status), ("rejected", "done"))
        with self.assertRaises(BusinessError):
            scheduler.retry_job(self.platform, job.id, reason="旧任务不能复活")
        self.assertEqual(Card.objects.count(), 0)

    def test_authority_and_contract_rechecked_at_execution(self):
        job = self.queue()
        self.platform.membership.active = False
        self.platform.membership.save(update_fields=["active"])
        jobs.run_one()
        job.refresh_from_db()
        self.assertEqual(job.status, "failed")
        self.assertEqual(job.last_error_code, "approval_authority_expired")
        self.platform.membership.active = True
        self.platform.membership.save(update_fields=["active"])
        scheduler.retry_job(self.platform, job.id, reason="有效管理员复核")
        self.product.status = "disabled"
        self.product.save(update_fields=["status"])
        jobs.run_one()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "issue_failed")
        self.assertEqual(Card.objects.count(), 0)
        pending = sales.request_stop(
            self.resource,
            self.order.id,
            action="cancel",
            version=self.order.version,
            reason="放弃本次申请",
        )
        sales.review_stop(
            self.platform,
            self.order.id,
            approved=True,
            version=pending.version,
            reason="核验未开卡",
        )
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "cancelled")

    def test_api_duplicate_review_key_does_not_create_two_jobs(self):
        client = api_client(self.platform)
        payload = {"approved": True, "version": self.order.version, "reason": "批量审核"}
        url = f"/api/v1/sales-orders/{self.order.id}/review"
        first = client.post(url, payload, HTTP_IDEMPOTENCY_KEY="issue-review-test", format="json")
        second = client.post(url, payload, HTTP_IDEMPOTENCY_KEY="issue-review-test", format="json")
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(first.data, second.data)
        self.assertEqual(Outbox.objects.filter(kind="sales.issue").count(), 1)
        self.assertEqual(first.data["status"], "issuing")
        self.assertIsNone(first.data["number_range"])

    def test_failed_import_retry_restores_phase_and_does_not_silently_skip(self):
        asset = files.upload_file(
            self.resource,
            data=xlsx_bytes([["姓名", "手机号", "数量"], ["合成客户", "13900000555", 1]]),
            filename="synthetic.xlsx",
            purpose="sales_excel",
        )
        batch = imports.create_import(self.resource, asset.id)
        # Simulate a queued batch left by the previous deployment.
        batch.status = "queued"
        batch.save(update_fields=["status"])
        job = Outbox.objects.create(
            kind="excel.inspect",
            dedup_key=f"legacy.inspect:{batch.id}",
            payload={"batch_id": str(batch.id), "version": batch.version},
            available_at=timezone.now(),
        )
        with patch(
            "chihuitong.services.imports.open_book",
            side_effect=BusinessError("synthetic_failure", "合成读取失败", 409),
        ):
            jobs.run_one()
        batch.refresh_from_db()
        self.assertEqual(batch.status, "failed")
        scheduler.retry_job(self.platform, job.id, reason="读取环境已恢复")
        jobs.run_one()
        batch.refresh_from_db()
        self.assertEqual(batch.status, "mapping")
        self.assertTrue(batch.preview)
