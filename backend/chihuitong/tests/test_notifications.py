import io
import json
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from chihuitong.errors import BusinessError
from chihuitong.integrations.tencent_sms import TencentSMS, tc3_headers
from chihuitong.models import Notification, Outbox, SmsDelivery, SmsTemplate
from chihuitong.services import appointments, jobs, notifications, scheduler

from . import test_finance
from .support import api_client
from .test_appointments import appointment_setup, confirmed_appointment


class MemoryBusinessSMS:
    sent = []
    fail = False

    def send_template(self, phone, template, parameters, *, context):
        if self.fail:
            raise BusinessError("sms_network_unknown", "合成发送未决", 503)
        self.sent.append((phone, template.code, parameters, context))
        return "SYNTHETIC-SMS-001"


class NotificationTests(TestCase):
    def setUp(self):
        appointment_setup(self)
        notifications.seed_templates()
        MemoryBusinessSMS.sent = []
        MemoryBusinessSMS.fail = False

    def enable(self, code="appointment.new"):
        template = SmsTemplate.objects.get(code=code)
        return notifications.configure_template(
            self.platform,
            code,
            content=template.content,
            parameter_names=template.parameter_names,
            provider_template_id="100001",
            sign_name="合成测试",
            status="active",
            version=template.version,
            reason="合成报备配置",
        )

    def test_template_platform_only_and_parameter_allowlist(self):
        template = self.enable()
        with self.assertRaises(BusinessError):
            notifications.configure_template(
                self.channel,
                template.code,
                content=template.content,
                parameter_names=template.parameter_names,
                provider_template_id="100001",
                sign_name="合成",
                status="active",
                version=template.version,
                reason="越权",
            )
        with self.assertRaises(BusinessError):
            notifications.configure_template(
                self.platform,
                template.code,
                content="任意客户{phone}",
                parameter_names=["phone"],
                provider_template_id="100001",
                sign_name="合成",
                status="active",
                version=template.version,
                reason="变量越界",
            )
        self.assertEqual(api_client(self.channel).get("/api/v1/sms-templates").status_code, 403)
        notifications.seed_templates()
        template.refresh_from_db()
        self.assertEqual(template.status, "active")

    def test_read_notification_does_not_confirm_appointment_and_is_scoped(self):
        appointment = appointments.book(
            self.customer.id,
            benefit_id=self.benefit.id,
            clinic_id=self.clinic.id,
            requested_at=self.scheduled,
        )
        notice = Notification.objects.get(recipient=self.clinic_actor.membership)
        self.assertEqual(
            api_client(self.channel).post(f"/api/v1/notifications/{notice.id}/read").status_code,
            404,
        )
        result = api_client(self.clinic_actor).post(f"/api/v1/notifications/{notice.id}/read")
        self.assertEqual(result.status_code, 200)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "pending")
        self.assertEqual(api_client(self.resource).get("/api/v1/notifications").data["total"], 0)

    @override_settings(SMS_BACKEND="chihuitong.tests.test_notifications.MemoryBusinessSMS")
    def test_sms_retry_and_accepted_delivery_not_sent_twice(self):
        self.enable()
        appointment = appointments.book(
            self.customer.id,
            benefit_id=self.benefit.id,
            clinic_id=self.clinic.id,
            requested_at=self.scheduled,
        )
        job = Outbox.objects.get(kind="sms.business")
        MemoryBusinessSMS.fail = True
        jobs.run_one()
        job.refresh_from_db()
        self.assertEqual(job.status, "pending")
        self.assertEqual(SmsDelivery.objects.get().status, "unknown")
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "pending")
        MemoryBusinessSMS.fail = False
        new_template = self.enable()
        Outbox.objects.filter(pk=job.id).update(available_at=timezone.now())
        jobs.run_one()
        self.assertEqual(SmsDelivery.objects.get().status, "accepted")
        notifications.send_business(job)
        self.assertEqual(len(MemoryBusinessSMS.sent), 1)
        self.assertNotIn(self.customer.name, str(MemoryBusinessSMS.sent))
        delivery = SmsDelivery.objects.get()
        self.assertEqual(delivery.template_version, new_template.version)
        history = list(delivery.history.order_by("number"))
        self.assertEqual([item.status for item in history], ["unknown", "accepted"])
        self.assertLess(history[0].template_version, history[1].template_version)
        response = api_client(self.platform).get(f"/api/v1/sms-deliveries/{delivery.id}/attempts")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self.customer.phone, str(response.data))

    def test_scheduler_24_72_and_expired_reschedule_requeues(self):
        item = confirmed_appointment(self)
        with patch("django.utils.timezone.now", return_value=self.scheduled + timedelta(hours=70)):
            appointments.reschedule(
                item.id,
                proposed_at=self.scheduled + timedelta(days=10),
                version=item.version,
                customer_id=self.customer.id,
            )
        for hours, expected in [(72, "success"), (95, "completed")]:
            with patch(
                "django.utils.timezone.now", return_value=self.scheduled + timedelta(hours=hours)
            ):
                scheduler.tick()
                count = Outbox.objects.filter(kind="appointment.deadline").count()
                scheduler.tick()
                self.assertEqual(Outbox.objects.filter(kind="appointment.deadline").count(), count)
                Outbox.objects.exclude(kind="appointment.deadline").update(
                    available_at=timezone.now() + timedelta(days=100)
                )
                jobs.run_one()
            item.refresh_from_db()
            self.assertEqual(item.status, expected)

    def test_job_retry_is_platform_only_and_no_payload_leak(self):
        job = Outbox.objects.create(
            kind="sms.business",
            dedup_key="synthetic-job",
            payload={"phone": "13900000999"},
            status="failed",
            available_at=timezone.now(),
            last_error_code="sms_unavailable",
        )
        self.assertEqual(api_client(self.channel).get("/api/v1/jobs").status_code, 403)
        response = api_client(self.platform).get("/api/v1/jobs")
        self.assertNotIn("13900000999", str(response.data))
        retried = scheduler.retry_job(self.platform, job.id, reason="配置已补齐")
        self.assertEqual(retried.status, "pending")

    def test_expired_worker_cannot_overwrite_a_new_claim_with_same_attempt_number(self):
        job = Outbox.objects.create(
            kind="appointment.deadline",
            dedup_key="claim-fence-test",
            payload={"appointment_id": str(uuid.uuid4())},
            available_at=timezone.now(),
        )
        new_token = uuid.uuid4()

        def stale_handler(*args, **kwargs):
            Outbox.objects.filter(pk=job.id).update(
                claim_token=new_token, attempts=1, status="running"
            )
            raise BusinessError("stale_worker", "旧执行器返回失败", 409)

        with patch("chihuitong.services.appointments.process_deadline", side_effect=stale_handler):
            jobs.run_one()
        job.refresh_from_db()
        self.assertEqual(job.status, "running")
        self.assertEqual(job.claim_token, new_token)
        self.assertEqual(job.last_error_code, "")

    def test_calendar_override_platform_only(self):
        client = api_client(self.platform)
        result = client.post(
            "/api/v1/calendar/2026-09-13", {"working": True, "note": "合成调休测试"}, format="json"
        )
        self.assertEqual(result.status_code, 200)
        self.assertTrue(client.get("/api/v1/calendar/2026-09-13").data["working"])
        self.assertEqual(
            api_client(self.channel).get("/api/v1/calendar/2026-09-13").status_code, 403
        )

    @override_settings(
        TENCENT_SMS={
            "secret_id": "SYNTHETIC",
            "secret_key": "SYNTHETIC-SECRET",
            "sdk_app_id": "1400000001",
            "region": "ap-beijing",
        }
    )
    def test_tencent_adapter_acceptance_and_failures(self):
        template = self.enable()
        raw = json.dumps(
            {
                "Response": {
                    "SendStatusSet": [
                        {
                            "Code": "Ok",
                            "SerialNo": "SYNTHETIC-SERIAL",
                            "PhoneNumber": "+8613900000099",
                        }
                    ]
                }
            }
        ).encode()
        with patch("urllib.request.OpenerDirector.open", return_value=io.BytesIO(raw)) as call:
            result = TencentSMS().send_template(
                "13900000099", template, {"appointment_number": "SYNTH001"}, context="synthetic"
            )
            self.assertEqual(result, "SYNTHETIC-SERIAL")
            request = call.call_args.args[0]
            self.assertEqual(request.host, "sms.tencentcloudapi.com")
            self.assertIn("TC3-HMAC-SHA256", request.get_header("Authorization"))
        with patch(
            "urllib.request.OpenerDirector.open",
            return_value=io.BytesIO(b'{"Response":{"Error":{"Code":"Denied"}}}'),
        ):
            with self.assertRaises(BusinessError):
                TencentSMS().send_template(
                    "13900000099", template, {"appointment_number": "SYNTH001"}, context="synthetic"
                )
        headers = tc3_headers("SYNTHETIC", "SYNTHETIC-SECRET", "ap-beijing", b"{}", timestamp=0)
        self.assertIn("1970-01-01/sms/tc3_request", headers["Authorization"])


class BillingNotificationTests(TestCase):
    setUp = test_finance.FinanceTests.setUp

    def test_daily_reminder_once_overdue_once_never_auto_offline(self):
        with patch("django.utils.timezone.now", return_value=self.clock):
            scheduler.tick()
            scheduler.tick()
            self.assertEqual(
                Outbox.objects.filter(kind="sms.business", payload__isnull=False)
                .exclude(dedup_key__startswith="appointment")
                .filter(dedup_key__startswith="bill-sms")
                .count(),
                2,
            )
        for delta in [1, 2]:
            with patch(
                "django.utils.timezone.now", return_value=self.bill.due_at + timedelta(days=delta)
            ):
                scheduler.tick()
        self.assertEqual(
            Outbox.objects.filter(
                dedup_key__startswith="bill-sms", dedup_key__endswith=":overdue"
            ).count(),
            2,
        )
        self.clinic.refresh_from_db()
        self.assertEqual(self.clinic.service_status, "online")
