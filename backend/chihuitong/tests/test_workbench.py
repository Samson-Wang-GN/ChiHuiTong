from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from chihuitong.errors import BusinessError
from chihuitong.models import AuditEvent, ContractVersion, Membership
from chihuitong.services import appointments, contracts, organizations, workbench

from .support import actor_fixture, api_client
from .test_appointments import appointment_setup, confirmed_appointment


class WorkbenchTests(TestCase):
    def setUp(self):
        appointment_setup(self)

    def test_role_workbenches_and_employee_exclusions(self):
        item = appointments.book(self.customer.id, benefit_id=self.benefit.id, clinic_id=self.clinic.id, requested_at=self.scheduled)
        employee = actor_fixture("clinic", "13900000061", "staff", self.clinic_actor.organization)
        for actor in [self.platform, self.resource, self.staff, self.channel, self.clinic_actor, employee]:
            response = api_client(actor).get("/api/v1/workbench")
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(response.data["kind"], actor.organization.kind)
            if actor == employee:
                self.assertNotIn("clinic_payment", response.data["tasks"]["categories"])
                self.assertNotIn("contract_submission", response.data["tasks"]["categories"])
                self.assertEqual(response.data["tasks"]["counts"]["pending"], 1)
        detail = api_client(employee).get(f"/api/v1/workbench/tasks/appointment_confirmation/{item.id}")
        self.assertEqual(detail.status_code, 200)
        self.assertIn("confirm", detail.data["actions"])
        self.assertEqual(detail.data["record"]["phone"], self.customer.phone)
        self.assertEqual(api_client(self.channel).get(f"/api/v1/workbench/tasks/appointment_confirmation/{item.id}").status_code, 404)

    def test_task_processed_state_tracks_real_operation_not_read(self):
        item = appointments.book(self.customer.id, benefit_id=self.benefit.id, clinic_id=self.clinic.id, requested_at=self.scheduled)
        before = workbench.list_tasks(self.clinic_actor, category="appointment_confirmation")
        self.assertEqual(before["counts"]["pending"], 1)
        workbench.task_detail(self.clinic_actor, "appointment_confirmation", item.id)
        self.assertEqual(workbench.list_tasks(self.clinic_actor, category="appointment_confirmation")["counts"]["pending"], 1)
        appointments.confirm(self.clinic_actor, item.id, scheduled_at=self.scheduled, version=item.version)
        after = workbench.list_tasks(self.clinic_actor, category="appointment_confirmation", status="processed")
        self.assertEqual(after["total"], 1)
        self.assertEqual(workbench.task_detail(self.clinic_actor, "appointment_confirmation", item.id)["actions"], [])

    def test_institution_review_and_account_cannot_be_used_before_approval(self):
        org = organizations.create_organization(self.platform, name="合成待审机构", kind="insurance",
            admin_name="合成初始管理员", admin_phone="13900000062")
        member = Membership.objects.get(organization=org)
        self.assertEqual(org.status, "pending")
        from chihuitong.services.common import Actor
        pending_actor = Actor(member)
        self.assertEqual(api_client(pending_actor).get("/api/v1/workbench").status_code, 403)
        with self.assertRaises(BusinessError):
            organizations.set_organization_status(self.platform, org.id, status="active", version=org.version, reason="不可绕过审核")
        task = workbench.task_detail(self.platform, "organization_review", org.id)
        self.assertEqual(task["status"], "pending")
        org = organizations.review_organization(self.platform, org.id, approved=False, version=org.version, reason="联系人需核对")
        org = organizations.update_organization(self.platform, org.id, name=org.name, contact_name="合成联系人",
            contact_phone="13900000063", version=org.version, reason="修正信息")
        org = organizations.resubmit_organization(self.platform, org.id, version=org.version, reason="资料已修正")
        organizations.review_organization(self.platform, org.id, approved=True, version=org.version, reason="核验通过")
        self.assertEqual(api_client(pending_actor).get("/api/v1/workbench").status_code, 200)
        self.assertTrue(member.platform_created)

    def test_object_logs_scoped_and_actor_role_snapshot(self):
        item = confirmed_appointment(self)
        self.clinic_actor.membership.role = "staff"
        self.clinic_actor.membership.save(update_fields=["role"])
        response = api_client(self.clinic_actor).get(f"/api/v1/objects/appointment/{item.id}/logs")
        self.assertEqual(response.status_code, 200, response.data)
        confirmed = next(row for row in response.data["results"] if row["action"] == "appointment.confirmed")
        self.assertEqual(confirmed["role"], "admin")
        self.assertNotIn(self.customer.phone, str(response.data))
        other = actor_fixture("clinic", "13900000064")
        self.assertEqual(api_client(other).get(f"/api/v1/objects/appointment/{item.id}/logs").status_code, 404)

    def test_contract_draft_edit_freeze_and_termination(self):
        previous = ContractVersion.objects.filter(contract__organization=self.resource.organization).first()
        data = {"starts_at": timezone.now(), "ends_at": timezone.now() + timedelta(days=365),
                "contact": previous.contact, "attachment_ids": previous.attachment_ids, "settlement_cycle": "monthly"}
        draft = contracts.create_version(self.platform, self.resource.organization.id, number=previous.contract.number, data=data)
        data["ends_at"] += timedelta(days=1)
        draft = contracts.edit_draft(self.platform, draft.id, data=data, version=draft.version, reason="修订草稿")
        pending = contracts.submit_version(self.platform, draft.id, version=draft.version)
        with self.assertRaises(BusinessError):
            contracts.edit_draft(self.platform, draft.id, data=data, version=pending.version, reason="待审不可改")
        approved = contracts.review_version(self.platform, pending.id, approved=True, version=pending.version, reason="核验通过")
        terminated = contracts.terminate(self.platform, approved.id, version=approved.version, reason="合作终止")
        self.assertEqual(terminated.status, "terminated")
        with self.assertRaises(BusinessError):
            contracts.current_contract(self.resource.organization.id)
        self.assertEqual(contracts.current_contract(self.resource.organization.id, stock=True).id, terminated.id)
        self.assertTrue(AuditEvent.objects.filter(object_id=previous.contract_id, action="contract.terminated").exists())
