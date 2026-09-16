from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from chihuitong.errors import BusinessError
from chihuitong.models import AgreementClinic, ClinicAgreement, ClinicCooperation, ClinicBill, ReceiptLedger, Redemption
from chihuitong.services import appointments, cooperations, finance, instant

from .support import actor_fixture, api_client
from .test_appointments import appointment_setup, confirmed_appointment


@override_settings(ACCEPTANCE_ENABLED=True, ACCEPTANCE_SIMULATED_EXTERNALS=True, ENVIRONMENT="test", WECHAT_PAY_ENABLED=False)
class CooperationTests(TestCase):
    def setUp(self):
        appointment_setup(self)
        self.hq = actor_fixture("clinic", "13900000055")
        self.subject = ClinicCooperation.objects.create(organization=self.hq.organization, kind="chain", created_by=self.channel.membership)
        self.clinic.cooperation = self.subject
        self.clinic.save(update_fields=["cooperation"])
        now = timezone.now()
        self.agreement = ClinicAgreement.objects.create(cooperation=self.subject, number="SYNTH-001", revision=1, status="approved", starts_at=now-timedelta(days=1), ends_at=now+timedelta(days=365), reviewed_at=now, payment_mode="postpaid", settlement_cycle="monthly", contact={"name":"合成联系人","phone":"13900000055"}, product_ids=[str(self.product.id)])
        AgreementClinic.objects.create(agreement=self.agreement, clinic=self.clinic)

    def test_subject_scope_and_headquarters_no_patient_access(self):
        appointment = confirmed_appointment(self)
        self.assertFalse(appointments.visible_appointments(self.hq).filter(pk=appointment.id).exists())
        self.assertTrue(cooperations.full_access(self.hq, self.subject))
        self.assertFalse(cooperations.full_access(self.clinic_actor, self.subject))
        self.assertEqual(api_client(self.clinic_actor).get(f"/api/v1/clinic-agreements/{self.agreement.id}").data["signed_attachment_ids"], [])

    def test_chain_bills_keep_old_debt_and_scope_store_payments(self):
        appointment = confirmed_appointment(self)
        with patch("django.utils.timezone.now", return_value=self.scheduled+timedelta(hours=1)):
            record = appointments.redeem(self.clinic_actor, appointment.id, credential=self.card.credential, confirmed=True, version=appointment.version)
        self.assertEqual(record.cooperation_id, self.subject.id)
        date = timezone.localdate(self.scheduled)
        issue = (date.replace(day=28)+timedelta(days=4)).replace(day=1)
        bill = finance.generate_cooperation_bill(self.subject.id, issued_on=issue)
        self.assertIsNone(bill.clinic_id)
        self.assertEqual(finance.generate_cooperation_bill(self.subject.id, issued_on=issue).id, bill.id)
        with self.assertRaises(BusinessError):
            finance.get_bill(self.clinic_actor, bill.id, pay=True)
        self.assertEqual(finance.get_bill(self.hq, bill.id, pay=True).id, bill.id)
        self.assertEqual(finance.scoped_bill_lines(self.clinic_actor, bill).count(), 1)
        finance.record_funds(bill, reference_index="1"*64, amount_cents=bill.total_cents, received_at=timezone.now(), kind="offline", source_id=bill.id)
        record.refresh_from_db()
        self.assertIsNotNone(record.settled_at)

    def instant_setup(self):
        self.subject.kind = "single"
        self.subject.save(update_fields=["kind"])
        self.agreement.payment_mode, self.agreement.settlement_cycle = "instant", ""
        self.agreement.save(update_fields=["payment_mode", "settlement_cycle"])
        appointment = confirmed_appointment(self)
        return appointment

    def test_instant_paid_once_completed_once_and_no_periodic_bill(self):
        appointment = self.instant_setup()
        with patch("django.utils.timezone.now", return_value=self.scheduled+timedelta(hours=1)), self.captureOnCommitCallbacks(execute=True):
            quote = appointments.redemption_quote(self.clinic_actor, appointment.id, credential=self.card.credential)
            args = dict(credential=self.card.credential, confirmed=True, version=quote["version"], quote=quote["quote"], key="synthetic-instant-001")
            item = instant.create(self.clinic_actor, appointment.id, **args)
        item.refresh_from_db()
        self.assertEqual(item.status, "completed")
        self.assertEqual(ReceiptLedger.objects.filter(instant_order=item).count(), 1)
        self.assertEqual(Redemption.objects.filter(appointment=appointment).count(), 1)
        self.assertIsNotNone(item.redemption.settled_at)
        self.assertEqual(ClinicBill.objects.count(), 0)
        self.assertEqual(instant.create(self.clinic_actor, appointment.id, **args).id, item.id)
        with self.assertRaises(BusinessError):
            appointments.reverse_redemption(self.clinic_actor, item.redemption_id, version=item.redemption.version, reason="错误核销")

    def test_pending_blocks_appointment_and_does_not_release_on_deadline(self):
        appointment = self.instant_setup()
        with patch("django.utils.timezone.now", return_value=self.scheduled+timedelta(hours=1)), patch("chihuitong.services.instant.prepare"):
            quote = appointments.redemption_quote(self.clinic_actor, appointment.id, credential=self.card.credential)
            item = instant.create(self.clinic_actor, appointment.id, credential=self.card.credential, confirmed=True, version=quote["version"], quote=quote["quote"], key="synthetic-pending-001")
        with self.assertRaises(BusinessError):
            appointments.cancel(appointment.id, customer_id=self.customer.id, version=appointment.version, reason="未到诊")
        appointments.process_deadline(appointment.id, now=self.scheduled+timedelta(hours=80))
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "success")
        self.assertTrue(appointment.reserved)
        self.assertEqual(item.status, "pending")

    def test_paid_failure_keeps_receipt_and_retries_without_payment(self):
        appointment = self.instant_setup()
        with patch("django.utils.timezone.now", return_value=self.scheduled+timedelta(hours=1)), self.captureOnCommitCallbacks(execute=True):
            quote = appointments.redemption_quote(self.clinic_actor, appointment.id, credential=self.card.credential)
            with patch("chihuitong.services.instant.complete", side_effect=BusinessError("temporary", "需重试", 503)):
                item = instant.create(self.clinic_actor, appointment.id, credential=self.card.credential, confirmed=True, version=quote["version"], quote=quote["quote"], key="synthetic-retry-001")
                instant.try_complete(item.id)
        item.refresh_from_db()
        self.assertEqual(item.receipts.count(), 1)
        with patch("django.utils.timezone.now", return_value=self.scheduled+timedelta(hours=1)):
            instant.complete(item.id)
            instant.complete(item.id)
        self.assertEqual(Redemption.objects.filter(appointment=appointment).count(), 1)

    def test_contract_final_approval_requires_originals_and_full_signed_pages(self):
        self.agreement.status = "pending"
        self.agreement.save(update_fields=["status"])
        with self.assertRaises(BusinessError):
            cooperations.review_agreement(self.platform, self.agreement.id, version=self.agreement.version, approved=True, reason="审核", final=True)

    def test_real_instant_activation_requires_acceptance(self):
        with override_settings(ACCEPTANCE_SIMULATED_EXTERNALS=False, INSTANT_PAYMENT_ACCEPTED=False), self.assertRaises(BusinessError):
            cooperations.assert_payment_ready()
