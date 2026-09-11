from datetime import datetime, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from chihuitong.errors import BusinessError
from chihuitong.models import PartnerBill, PartnerBillLine, Redemption
from chihuitong.services import appointments, files, finance

from .support import actor_fixture
from .test_appointments import appointment_setup, confirmed_appointment
from .test_catalog import image_bytes


class FinanceTests(TestCase):
    def setUp(self):
        appointment_setup(self)
        self.appointment = confirmed_appointment(self)
        self.service_time = self.scheduled + timedelta(hours=1)
        with patch("django.utils.timezone.now", return_value=self.service_time):
            self.redemption = appointments.redeem(
                self.clinic_actor,
                self.appointment.id,
                credential=self.card.credential,
                confirmed=True,
                version=self.appointment.version,
            )
        date = timezone.localtime(self.service_time).date()
        self.issue_date = (date.replace(day=28) + timedelta(days=4)).replace(day=1)
        self.clock = timezone.make_aware(
            datetime.combine(self.issue_date, datetime.min.time())
        ) + timedelta(hours=12)
        with patch("django.utils.timezone.now", return_value=self.clock):
            self.bill = finance.generate_clinic_bill(self.clinic.id, issued_on=self.issue_date)
        self.proof = files.upload_file(
            self.clinic_actor, data=image_bytes(), filename="合成门诊付款.png", purpose="payment"
        )

    def pay_clinic(self, amount=None, reference="CLINIC-SYNTH-001"):
        self.bill.refresh_from_db()
        receipt = finance.submit_receipt(
            self.clinic_actor,
            self.bill.id,
            amount_cents=amount or self.bill.total_cents,
            paid_at=timezone.now(),
            payer="合成门诊",
            reference=reference,
            attachment_ids=[str(self.proof.id)],
            version=self.bill.version,
        )
        finance.review_receipt(
            self.platform,
            receipt.id,
            approved=True,
            version=receipt.version,
            reason="实际到账已核对",
        )
        self.bill.refresh_from_db()
        return receipt

    def test_calendar_deadlines_and_idempotent_issue(self):
        self.assertEqual(
            finance.due_at(self.issue_date, "monthly").date(), self.issue_date + timedelta(days=5)
        )
        self.assertEqual(
            finance.due_at(self.issue_date, "weekly").date(), self.issue_date + timedelta(days=3)
        )
        self.assertEqual(
            finance.generate_clinic_bill(self.clinic.id, issued_on=self.issue_date).id, self.bill.id
        )
        self.assertEqual(self.bill.lines.count(), 1)

    def test_partner_feedback_suspends_confirmation_until_platform_response(self):
        with patch("django.utils.timezone.now", return_value=self.clock):
            self.pay_clinic()
            next_month = (self.issue_date.replace(day=28) + timedelta(days=4)).replace(day=1)
            finance.generate_partner_bills(issued_on=next_month)
            bill = PartnerBill.objects.get(organization=self.resource.organization)
            original = (bill.total_cents, bill.due_at)
            feedback = finance.submit_feedback(
                self.resource, bill.id, partner=True, message="请复核这笔合成交易", version=bill.version
            )
            bill.refresh_from_db()
            self.assertEqual(bill.status, "disputed")
            with self.assertRaises(BusinessError):
                finance.confirm_partner_bill(self.resource, bill.id, version=bill.version, confirmed=True)
            finance.respond_feedback(
                self.platform, feedback.id, response="已核对原始交易", version=feedback.version
            )
            bill.refresh_from_db()
            self.assertEqual(bill.status, "pending_confirmation")
            self.assertEqual((bill.total_cents, bill.due_at), original)
            finance.confirm_partner_bill(self.resource, bill.id, version=bill.version, confirmed=True)

    def test_partial_receipt_does_not_settle_and_blocks_partner_pool(self):
        with patch("django.utils.timezone.now", return_value=self.clock):
            self.pay_clinic(1000)
            self.assertEqual(self.bill.status, "open")
            self.redemption.refresh_from_db()
            self.assertIsNone(self.redemption.settled_at)
            future_issue = (self.issue_date.replace(day=28) + timedelta(days=4)).replace(day=1)
            self.assertEqual(finance.generate_partner_bills(issued_on=future_issue), [])
            self.pay_clinic(5000, "CLINIC-SYNTH-002")
            self.assertEqual(self.bill.status, "settled")
            self.redemption.refresh_from_db()
            self.assertIsNotNone(self.redemption.settled_at)

    def test_pending_receipt_blocks_reversal_and_paid_prevents_reversal(self):
        with patch("django.utils.timezone.now", return_value=self.clock):
            receipt = finance.submit_receipt(
                self.clinic_actor,
                self.bill.id,
                amount_cents=6000,
                paid_at=timezone.now(),
                payer="合成门诊",
                reference="CLINIC-SYNTH-003",
                attachment_ids=[str(self.proof.id)],
                version=self.bill.version,
            )
            with self.assertRaises(BusinessError):
                appointments.reverse_redemption(
                    self.clinic_actor,
                    self.redemption.id,
                    version=self.redemption.version,
                    reason="待审阻断",
                )
            finance.review_receipt(
                self.platform,
                receipt.id,
                approved=True,
                version=receipt.version,
                reason="实际全额到账",
            )
            with self.assertRaises(BusinessError):
                appointments.reverse_redemption(
                    self.clinic_actor,
                    self.redemption.id,
                    version=self.redemption.version,
                    reason="结清阻断",
                )

    def test_unsettled_reversal_removes_active_line_and_preserves_history(self):
        appointments.reverse_redemption(
            self.clinic_actor,
            self.redemption.id,
            version=self.redemption.version,
            reason="未结清错误核销",
        )
        self.bill.refresh_from_db()
        self.assertEqual((self.bill.total_cents, self.bill.status), (0, "cancelled"))
        self.assertEqual(self.bill.lines.count(), 1)
        self.assertEqual(self.bill.lines.filter(active=True).count(), 0)
        self.assertEqual(self.bill.revisions.count(), 2)

    def test_history_collected_after_clinic_full_payment_once(self):
        with patch("django.utils.timezone.now", return_value=self.clock):
            self.assertEqual(finance.generate_partner_bills(issued_on=self.issue_date), [])
            self.pay_clinic()
            future_issue = (self.issue_date.replace(day=28) + timedelta(days=4)).replace(day=1)
            bills = finance.generate_partner_bills(issued_on=future_issue)
            self.assertEqual(len(bills), 2)
            self.assertEqual(PartnerBillLine.objects.count(), 2)
            self.assertFalse(
                PartnerBill.objects.filter(organization=self.platform.organization).exists()
            )
            finance.generate_partner_bills(issued_on=future_issue)
            self.assertEqual(PartnerBillLine.objects.count(), 2)
            self.assertEqual(PartnerBill.objects.count(), 2)

    def test_zero_share_bill_terminal_without_fake_payment(self):
        Redemption.objects.filter(pk=self.redemption.id).update(
            resource_cents=0, platform_cents=4800
        )
        with patch("django.utils.timezone.now", return_value=self.clock):
            self.pay_clinic()
            future_issue = (self.issue_date.replace(day=28) + timedelta(days=4)).replace(day=1)
            finance.generate_partner_bills(issued_on=future_issue)
            bill = PartnerBill.objects.get(organization=self.resource.organization)
            self.assertEqual((bill.total_cents, bill.status), (0, "no_payment"))
            with self.assertRaises(BusinessError):
                finance.confirm_partner_bill(
                    self.resource, bill.id, version=bill.version, confirmed=True
                )

    def test_partner_confirm_payment_receipt_flow_and_admin_boundary(self):
        with patch("django.utils.timezone.now", return_value=self.clock):
            self.pay_clinic()
        future_issue = (self.issue_date.replace(day=28) + timedelta(days=4)).replace(day=1)
        future_clock = timezone.make_aware(
            datetime.combine(future_issue, datetime.min.time())
        ) + timedelta(hours=12)
        with patch("django.utils.timezone.now", return_value=future_clock):
            finance.generate_partner_bills(issued_on=future_issue)
            bill = PartnerBill.objects.get(organization=self.resource.organization)
            with self.assertRaises(BusinessError):
                finance.confirm_partner_bill(
                    self.platform, bill.id, version=bill.version, confirmed=True
                )
            with self.assertRaises(BusinessError):
                finance.get_partner_bill(self.staff, bill.id, operate=True)
            bill = finance.confirm_partner_bill(
                self.resource, bill.id, version=bill.version, confirmed=True
            )
            proof = files.upload_file(
                self.platform, data=image_bytes(), filename="合成平台付款.png", purpose="payment"
            )
            bill = finance.pay_partner_bill(
                self.platform,
                bill.id,
                version=bill.version,
                amount_cents=bill.total_cents,
                paid_at=timezone.now(),
                reference="PARTNER-SYNTH-001",
                attachment_ids=[str(proof.id)],
                confirmed=True,
            )
            self.assertEqual(bill.status, "pending_receipt")
            bill = finance.receive_partner_bill(
                self.resource,
                bill.id,
                version=bill.version,
                actual_received_on=future_issue,
                confirmed=True,
            )
            self.assertEqual(bill.status, "completed")

    def test_clinic_employee_and_other_clinic_cannot_pay(self):
        employee = actor_fixture("clinic", "13900000051", "staff", self.clinic_actor.organization)
        other = actor_fixture("clinic", "13900000052")
        for actor in [employee, other, self.channel]:
            with self.assertRaises(BusinessError):
                finance.get_bill(actor, self.bill.id, pay=True)

    def test_overdue_is_display_only_does_not_take_clinic_offline(self):
        self.assertEqual(
            finance.effective_bill_status(self.bill, now=self.bill.due_at + timedelta(seconds=1)),
            "overdue",
        )
        self.clinic.refresh_from_db()
        self.assertEqual(self.clinic.service_status, "online")
