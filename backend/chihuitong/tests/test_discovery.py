from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone

from chihuitong.models import (
    AgreementClinic,
    Clinic,
    ClinicAgreement,
    ClinicCooperation,
    ClinicProduct,
    ContractVersion,
)
from chihuitong.services import files

from .support import actor_fixture
from .test_appointments import appointment_setup, confirmed_appointment
from .test_catalog import contract_fixture, image_bytes
from .test_mini import MINI_SETTINGS, mini_client


@override_settings(MINI_PROGRAMS=MINI_SETTINGS)
class DiscoveryTests(TestCase):
    def setUp(self):
        appointment_setup(self)
        self.client, _ = mini_client("customer", self.customer.phone)
        self.params = {"benefit_id": str(self.benefit.id)}

    def search(self, **values):
        return self.client.get("/api/v1/mini/customer/clinics", {**self.params, **values})

    def test_own_benefit_only_and_no_private_profile_exposure(self):
        result = self.search()
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result.data["total"], 1)
        self.assertNotIn("business_phone", result.data["results"][0])
        other, _ = mini_client("customer", "13900000881")
        self.assertEqual(other.get("/api/v1/mini/customer/clinics", self.params).status_code, 404)
        self.assertEqual(self.search(longitude="116.3").status_code, 400)
        self.assertEqual(self.search(longitude="NaN", latitude="30").status_code, 400)

    def test_offline_disabled_product_and_latest_expired_contract_excluded(self):
        for field, value in [("service_status", "offline"), ("review_status", "draft")]:
            Clinic.objects.filter(pk=self.clinic.id).update(**{field: value})
            self.assertEqual(self.search().data["total"], 0)
            Clinic.objects.filter(pk=self.clinic.id).update(**{field: getattr(self.clinic, field)})
        self.product.status = "disabled"
        self.product.save(update_fields=["status"])
        self.assertEqual(self.search().data["total"], 0)
        self.product.status = "active"
        self.product.save(update_fields=["status"])
        old = ContractVersion.objects.get(contract__organization=self.channel.organization)
        old.pk = None
        old.revision += 1
        old.starts_at = timezone.now() - timedelta(hours=2)
        old.ends_at = timezone.now() - timedelta(hours=1)
        old.save()
        self.assertEqual(self.search().data["total"], 0)

    def test_bilateral_contract_coverage_and_effective_dates(self):
        owner = actor_fixture("clinic", "13900000883")
        subject = ClinicCooperation.objects.create(
            organization=owner.organization, kind="chain", created_by=self.channel.membership
        )
        self.clinic.cooperation = subject
        self.clinic.save(update_fields=["cooperation"])
        now = timezone.now()
        agreement = ClinicAgreement.objects.create(
            cooperation=subject,
            submitted_by=self.channel.membership,
            number="SYNTH-DISCOVERY",
            revision=1,
            status="approved",
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=30),
            reviewed_at=now,
            payment_mode="postpaid",
            settlement_cycle="monthly",
            product_ids=[str(self.product.id)],
        )
        self.assertEqual(self.search().data["total"], 0)
        coverage = AgreementClinic.objects.create(agreement=agreement, clinic=self.clinic)
        self.assertEqual(self.search().data["total"], 1)
        agreement.product_ids = []
        agreement.save(update_fields=["product_ids"])
        self.assertEqual(self.search().data["total"], 0)
        agreement.product_ids = [str(self.product.id)]
        agreement.starts_at = now + timedelta(days=1)
        agreement.save(update_fields=["product_ids", "starts_at"])
        self.assertEqual(self.search().data["total"], 0)
        agreement.starts_at = now - timedelta(days=1)
        agreement.status = "terminated"
        agreement.save(update_fields=["starts_at", "status"])
        self.assertEqual(self.search().data["total"], 0)
        agreement.status = "approved"
        agreement.save(update_fields=["status"])
        response = self.client.post(
            "/api/v1/mini/customer/appointments",
            {
                "benefit_id": str(self.benefit.id),
                "clinic_id": str(self.clinic.id),
                "requested_at": self.scheduled.isoformat(),
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="synthetic-bilateral-booking",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertNotIn("clinic_settled", response.data)
        self.assertTrue(AgreementClinic.objects.filter(pk=coverage.pk).exists())

    def test_distance_order_pagination_and_unconfirmed_last(self):
        actor = actor_fixture("clinic", "13900000882")
        near = Clinic.objects.create(
            organization=actor.organization,
            channel=self.channel.organization,
            responsible=self.channel.membership,
            profile=self.clinic.profile,
            review_status="approved",
            profile_version=1,
            service_status="online",
            longitude=Decimal("116.300000"),
            latitude=Decimal("39.900000"),
        )
        contract_fixture(self.platform, actor.organization, submitter=self.channel)
        ClinicProduct.objects.create(clinic=near, product=self.product, status="online")
        result = self.search(longitude="116.300000", latitude="39.900000", page_size=1)
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result.data["total"], 2)
        self.assertEqual(result.data["results"][0]["id"], str(near.id))
        self.assertEqual(result.data["results"][0]["distance_m"], 0)
        second = self.search(longitude="116.300000", latitude="39.900000", page_size=1, page=2)
        self.assertIsNone(second.data["results"][0]["distance_m"])

    def test_published_cover_only_and_existing_appointment_can_contact_offline_clinic(self):
        asset = files.upload_file(
            self.channel, data=image_bytes(), filename="合成封面.png", purpose="cover"
        )
        self.clinic.profile = {**self.clinic.profile, "cover_id": str(asset.id)}
        self.clinic.save(update_fields=["profile"])
        url = f"/api/v1/mini/customer/clinics/{self.clinic.id}"
        self.assertEqual(self.client.get(url + "/cover", self.params).status_code, 200)
        confirmed_appointment(self)
        Clinic.objects.filter(pk=self.clinic.id).update(service_status="offline")
        detail = self.client.get(url)
        self.assertEqual(detail.status_code, 200, detail.data)
        self.assertEqual(detail.data["frontdesk_phone"], "13900000012")
        self.assertEqual(self.client.get(url + "/cover").status_code, 200)
        # Never expose qualification images through the cover endpoint even if corrupted metadata points at one.
        asset.purpose = "license"
        asset.save(update_fields=["purpose"])
        self.assertEqual(self.client.get(url + "/cover").status_code, 404)
