from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from chihuitong.errors import BusinessError
from chihuitong.models import (
    Benefit,
    Clinic,
    ClinicProduct,
    CustomerMessage,
    FulfillmentTask,
    Redemption,
)
from chihuitong.services import appointments, customers

from .support import actor_fixture
from .test_catalog import contract_fixture
from .test_sales import approve, order_fixture, sales_setup


def appointment_setup(test):
    sales_setup(test)
    test.channel = actor_fixture("channel", "13900000010")
    test.clinic_actor = actor_fixture("clinic", "13900000011")
    contract_fixture(test.platform, test.channel.organization, product=test.product)
    test.clinic = Clinic.objects.create(
        organization=test.clinic_actor.organization,
        channel=test.channel.organization,
        responsible=test.channel.membership,
        review_status="approved",
        profile_version=1,
        service_status="online",
        profile={
            "name": "合成门诊",
            "frontdesk_phone": "13900000012",
            "business_contact": "合成业务联系人",
            "business_phone": "010-12345678",
            "responsible_id": str(test.channel.membership.id),
        },
    )
    contract_fixture(test.platform, test.clinic_actor.organization, submitter=test.channel)
    ClinicProduct.objects.create(clinic=test.clinic, product=test.product, status="online")
    test.order = approve(test, order_fixture(test))
    test.customer = customers.register_verified_customer("13900000101")
    test.card = test.order.cards.order_by("serial").first()
    test.benefit = customers.claim(test.customer.id, test.card.id)
    test.scheduled = timezone.now() + timedelta(days=1)


def confirmed_appointment(test):
    appointment = appointments.book(
        test.customer.id,
        benefit_id=test.benefit.id,
        clinic_id=test.clinic.id,
        requested_at=test.scheduled,
    )
    return appointments.confirm(
        test.clinic_actor, appointment.id, scheduled_at=test.scheduled, version=appointment.version
    )


class AppointmentTests(TestCase):
    def setUp(self):
        appointment_setup(self)

    def test_booking_reserves_without_fee_and_clinic_confirmation(self):
        appointment = confirmed_appointment(self)
        self.assertEqual(appointment.status, "success")
        self.benefit.refresh_from_db()
        self.assertEqual(
            (self.benefit.available, self.benefit.reserved, self.benefit.used), (0, 1, 0)
        )
        self.assertEqual(Redemption.objects.count(), 0)
        with self.assertRaises(BusinessError):
            appointments.confirm(
                self.channel,
                appointment.id,
                scheduled_at=self.scheduled,
                version=appointment.version,
            )

    def test_appointment_and_reschedule_must_be_inside_expiry(self):
        with self.assertRaises(BusinessError):
            appointments.book(
                self.customer.id,
                benefit_id=self.benefit.id,
                clinic_id=self.clinic.id,
                requested_at=self.benefit.expires_at + timedelta(days=1),
            )
        appointment = confirmed_appointment(self)
        with self.assertRaises(BusinessError):
            appointments.reschedule(
                appointment.id,
                proposed_at=self.benefit.expires_at + timedelta(days=1),
                version=appointment.version,
                customer_id=self.customer.id,
            )

    def test_customer_reschedule_keeps_old_until_review_and_clinic_requires_agreement(self):
        appointment = confirmed_appointment(self)
        proposed = self.scheduled + timedelta(days=1)
        change = appointments.reschedule(
            appointment.id,
            proposed_at=proposed,
            version=appointment.version,
            customer_id=self.customer.id,
        )
        appointment.refresh_from_db()
        self.assertEqual(appointment.scheduled_at, self.scheduled)
        appointments.review_reschedule(
            self.clinic_actor, change.id, approved=True, version=change.version, reason="已协商"
        )
        appointment.refresh_from_db()
        self.assertEqual(appointment.scheduled_at, proposed)
        with self.assertRaises(BusinessError):
            appointments.reschedule(
                appointment.id,
                proposed_at=proposed + timedelta(days=1),
                version=appointment.version,
                actor=self.clinic_actor,
            )

    def test_pending_expiry_releases_once(self):
        appointment = appointments.book(
            self.customer.id,
            benefit_id=self.benefit.id,
            clinic_id=self.clinic.id,
            requested_at=self.scheduled,
        )
        appointments.process_deadline(appointment.id, now=appointment.pending_deadline)
        appointments.process_deadline(
            appointment.id, now=appointment.pending_deadline + timedelta(hours=1)
        )
        self.benefit.refresh_from_db()
        self.assertEqual((self.benefit.available, self.benefit.reserved), (1, 0))

    def test_24_hour_task_72_hour_system_completion_does_not_charge_or_release(self):
        appointment = confirmed_appointment(self)
        appointments.process_deadline(
            appointment.id, now=self.scheduled + timedelta(hours=24) - timedelta(seconds=1)
        )
        self.assertEqual(FulfillmentTask.objects.count(), 0)
        appointments.process_deadline(appointment.id, now=self.scheduled + timedelta(hours=24))
        self.assertEqual(FulfillmentTask.objects.filter(status="pending").count(), 1)
        appointments.process_deadline(appointment.id, now=self.scheduled + timedelta(hours=72))
        appointment.refresh_from_db()
        self.assertEqual(
            (appointment.status, appointment.completion_source), ("completed", "system")
        )
        self.assertEqual(Redemption.objects.count(), 0)
        self.assertEqual(FulfillmentTask.objects.filter(status="closed").count(), 1)
        self.assertEqual(CustomerMessage.objects.filter(status="pending").count(), 1)
        self.benefit.refresh_from_db()
        self.assertEqual(self.benefit.reserved, 1)

    def test_overdue_clinic_absence_retains_benefit_customer_releases(self):
        appointment = confirmed_appointment(self)
        with patch("django.utils.timezone.now", return_value=self.scheduled + timedelta(hours=25)):
            with self.assertRaises(BusinessError):
                appointments.cancel(
                    appointment.id,
                    version=appointment.version,
                    reason="不能直接释放",
                    actor=self.clinic_actor,
                )
            appointment = appointments.report_absent(
                self.clinic_actor, appointment.id, version=appointment.version, confirmed=True
            )
            self.benefit.refresh_from_db()
            self.assertEqual(self.benefit.reserved, 1)
            appointments.customer_feedback(
                self.customer.id,
                appointment.id,
                arrived=False,
                version=appointment.version,
                confirmed=True,
            )
        self.benefit.refresh_from_db()
        self.assertEqual((self.benefit.available, self.benefit.reserved), (1, 0))

    def test_absence_arrived_conflict_records_without_adjudicating(self):
        appointment = confirmed_appointment(self)
        with patch("django.utils.timezone.now", return_value=self.scheduled + timedelta(hours=25)):
            appointment = appointments.report_absent(
                self.clinic_actor, appointment.id, version=appointment.version, confirmed=True
            )
            appointment = appointments.customer_feedback(
                self.customer.id,
                appointment.id,
                arrived=True,
                version=appointment.version,
                confirmed=True,
            )
            self.assertTrue(appointment.conflict)
            with self.assertRaises(BusinessError):
                appointments.customer_feedback(
                    self.customer.id,
                    appointment.id,
                    arrived=False,
                    version=appointment.version,
                    confirmed=True,
                )

    def test_redeem_and_reversal_normal_preserve_occupied_amount(self):
        appointment = confirmed_appointment(self)
        with patch("django.utils.timezone.now", return_value=self.scheduled + timedelta(hours=1)):
            record = appointments.redeem(
                self.clinic_actor,
                appointment.id,
                credential=self.card.credential,
                confirmed=True,
                version=appointment.version,
            )
            self.assertEqual(record.fee_cents, 6000)
            self.assertEqual(
                appointments.redeem(
                    self.clinic_actor,
                    appointment.id,
                    credential=self.card.credential,
                    confirmed=True,
                    version=appointment.version,
                ).id,
                record.id,
            )
            appointments.reverse_redemption(
                self.clinic_actor, record.id, version=record.version, reason="错误核销"
            )
        appointment.refresh_from_db()
        self.benefit.refresh_from_db()
        self.assertEqual(appointment.status, "success")
        self.assertEqual(
            (self.benefit.available, self.benefit.reserved, self.benefit.used), (0, 1, 0)
        )

    def test_system_supplement_reversal_requires_separate_restoration(self):
        appointment = confirmed_appointment(self)
        with patch("django.utils.timezone.now", return_value=self.scheduled + timedelta(hours=73)):
            appointment = appointments.process_deadline(appointment.id)
            appointment = appointments.customer_feedback(
                self.customer.id,
                appointment.id,
                arrived=True,
                version=appointment.version,
                confirmed=True,
            )
            record = appointments.redeem(
                self.clinic_actor,
                appointment.id,
                credential=self.card.credential,
                confirmed=True,
                version=appointment.version,
            )
            appointments.reverse_redemption(
                self.clinic_actor, record.id, version=record.version, reason="补核销有误"
            )
            appointment.refresh_from_db()
            self.benefit.refresh_from_db()
            self.assertEqual(
                (appointment.status, appointment.completion_source), ("completed", "system")
            )
            self.assertEqual(
                (self.benefit.available, self.benefit.used, self.benefit.restoring), (0, 0, 1)
            )
            self.assertEqual(FulfillmentTask.objects.exclude(status="closed").count(), 0)
            appointments.restore_reversal(
                self.customer.id, appointment.id, version=appointment.version, confirmed=True
            )
        self.benefit.refresh_from_db()
        self.assertEqual((self.benefit.available, self.benefit.restoring), (1, 0))

    def test_redeem_after_expiry_uses_scheduled_date_and_settled_cannot_reverse(self):
        appointment = confirmed_appointment(self)
        Benefit.objects.filter(pk=self.benefit.id).update(
            expires_at=self.scheduled + timedelta(hours=1)
        )
        with patch("django.utils.timezone.now", return_value=self.scheduled + timedelta(days=2)):
            record = appointments.redeem(
                self.clinic_actor,
                appointment.id,
                credential=self.card.credential,
                confirmed=True,
                version=appointment.version,
            )
            Redemption.objects.filter(pk=record.id).update(settled_at=timezone.now())
            with self.assertRaises(BusinessError):
                appointments.reverse_redemption(
                    self.clinic_actor, record.id, version=record.version, reason="已结算阻断"
                )
