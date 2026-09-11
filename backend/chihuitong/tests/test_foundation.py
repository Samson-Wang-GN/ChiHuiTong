import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from chihuitong.crypto import normalize_phone
from chihuitong.errors import BusinessError
from chihuitong.identity import request_code, verify_code
from chihuitong.models import (
    Account,
    AuditEvent,
    IdempotencyRecord,
    LoginChallenge,
    Membership,
    Organization,
    Session,
)
from chihuitong.services.common import idempotent
from chihuitong.services.organizations import create_member, create_organization, update_member

from .support import MemorySMS, actor_fixture, api_client


class FoundationTests(TestCase):
    def setUp(self):
        self.platform = actor_fixture()
        self.resource = actor_fixture("broker", "13900000002")
        self.channel = actor_fixture("channel", "13900000003")
        self.staff = actor_fixture("broker", "13900000004", "staff", self.resource.organization)
        MemorySMS.messages.clear()

    def test_phone_normalization_and_rejection(self):
        for value in ["+86 139-0000-0001", "００８６１３９０００００００１", "13900000001"]:
            self.assertEqual(normalize_phone(value), "13900000001")
        for value in ["123", "+1 13900000001", True, 13900000001.0, "23900000001"]:
            with self.assertRaises(BusinessError):
                normalize_phone(value)

    def test_sensitive_values_encrypted_and_roundtrip(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT phone, name FROM chihuitong_account WHERE id=%s", [self.platform.account.id]
            )
            phone, name = cursor.fetchone()
        self.assertNotIn("13900000001", phone)
        self.assertNotIn("合成测试", name)
        saved = Account.objects.get(pk=self.platform.account.id)
        self.assertEqual(saved.phone, "13900000001")
        self.assertEqual(saved.name, "合成测试人员")

    def test_create_organization_protected_initial_admin_and_audit(self):
        org = create_organization(
            self.platform,
            name="合成资源方",
            kind="bank",
            admin_name="合成管理员",
            admin_phone="13900000005",
        )
        member = Membership.objects.get(organization=org)
        self.assertTrue(member.platform_created)
        with self.assertRaisesMessage(BusinessError, "平台开通"):
            update_member(
                self.platform, member.id, role="staff", active=True, version=1, reason="测试"
            )
        self.assertEqual(AuditEvent.objects.filter(object_id=org.id).count(), 1)
        with self.assertRaises(BusinessError):
            create_organization(
                self.resource,
                name="拒绝",
                kind="bank",
                admin_name="合成",
                admin_phone="13900000006",
            )

    def test_staff_cannot_manage_accounts_or_other_organization(self):
        for actor, org in [
            (self.staff, self.resource.organization),
            (self.resource, self.channel.organization),
        ]:
            with self.assertRaises(BusinessError):
                create_member(actor, org.id, name="合成", phone="13900000007", role="admin")

    def test_last_admin_and_self_change(self):
        with self.assertRaisesMessage(BusinessError, "最后一个管理员"):
            update_member(
                self.platform,
                self.resource.membership.id,
                role="staff",
                active=True,
                version=1,
                reason="测试",
            )
        with self.assertRaisesMessage(BusinessError, "自己"):
            update_member(
                self.resource,
                self.resource.membership.id,
                role="staff",
                active=True,
                version=1,
                reason="测试",
            )
        create_member(
            self.resource,
            self.resource.organization.id,
            name="合成新管理",
            phone="13900000008",
            role="admin",
        )
        member = update_member(
            self.platform,
            self.resource.membership.id,
            role="staff",
            active=True,
            version=1,
            reason="测试",
        )
        self.assertEqual(member.version, 2)
        with self.assertRaisesMessage(BusinessError, "记录已更新"):
            update_member(
                self.platform, member.id, role="admin", active=True, version=1, reason="旧页"
            )

    def test_api_auth_scope_and_unknown_field(self):
        url = "/api/v1/organizations"
        self.assertEqual(APIClient().get(url).status_code, 401)
        self.assertEqual(api_client(self.resource).get(url).status_code, 403)
        client = api_client(self.platform)
        response = client.post(
            url,
            {
                "name": "合成机构",
                "kind": "bank",
                "admin_name": "测试",
                "admin_phone": "13900000010",
                "status": "active",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        response = client.get(url + "?status=disabled")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 0)
        self.assertEqual(response.json()["counts"]["all"], 2)
        client.credentials(HTTP_X_MEMBERSHIP_ID=str(self.resource.membership.id))
        self.assertEqual(client.get(url).status_code, 401)

    def test_forged_membership_and_disabled_membership(self):
        client = api_client(self.resource)
        client._credentials["HTTP_X_MEMBERSHIP_ID"] = str(self.platform.membership.id)
        self.assertEqual(client.get("/api/v1/organizations").status_code, 403)
        client._credentials["HTTP_X_MEMBERSHIP_ID"] = "invalid"
        self.assertEqual(client.get("/api/v1/organizations").status_code, 403)
        client._credentials["HTTP_X_MEMBERSHIP_ID"] = str(self.resource.membership.id)
        Membership.objects.filter(pk=self.resource.membership.id).update(active=False)
        self.assertEqual(
            client.get(
                f"/api/v1/organizations/{self.resource.organization.id}/members"
            ).status_code,
            403,
        )

    @override_settings(SMS_BACKEND="chihuitong.tests.support.MemorySMS")
    def test_otp_single_use_and_session_revocation(self):
        response = request_code("13900000001", "test-ip")
        self.assertNotIn("code", response)
        phone, code = MemorySMS.messages[-1]
        credentials = verify_code(phone, code, "test-ip")
        with self.assertRaises(BusinessError):
            verify_code(phone, code, "test-ip")
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {credentials['token']}")
        response = client.get("/api/v1/auth/me")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(phone, response.content.decode())
        self.assertEqual(client.post("/api/v1/auth/logout").status_code, 200)
        self.assertEqual(client.get("/api/v1/auth/me").status_code, 401)
        self.assertNotEqual(Session.objects.first().token_digest, credentials["token"])

    @override_settings(SMS_BACKEND="chihuitong.tests.support.MemorySMS")
    def test_otp_failures_commit_and_cooldown(self):
        request_code("13900000001", "test-ip")
        with self.assertRaisesMessage(BusinessError, "稍后"):
            request_code("13900000001", "test-ip")
        actual_code = MemorySMS.messages[-1][1]
        wrong = "000000" if actual_code != "000000" else "000001"
        for _ in range(5):
            with self.assertRaises(BusinessError):
                verify_code("13900000001", wrong, "test-ip")
        self.assertEqual(LoginChallenge.objects.get().attempts, 5)
        with self.assertRaises(BusinessError):
            verify_code("13900000001", actual_code, "test-ip")
        self.assertEqual(Session.objects.count(), 0)

    @override_settings(SMS_BACKEND="chihuitong.tests.support.MemorySMS")
    def test_expired_and_unregistered_login_no_auto_staff(self):
        request_code("13900000001", "test-ip")
        LoginChallenge.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        with self.assertRaises(BusinessError):
            verify_code("13900000001", MemorySMS.messages[-1][1], "test-ip")
        request_code("13900009999", "test-ip")
        with self.assertRaises(BusinessError):
            verify_code("13900009999", MemorySMS.messages[-1][1], "test-ip")
        self.assertEqual(Account.objects.count(), 4)

    def test_missing_sms_configuration_fails_closed(self):
        with self.assertRaisesMessage(BusinessError, "尚未配置"):
            request_code("13900000001", "test-ip")
        self.assertFalse(LoginChallenge.objects.get().delivered)

    def test_idempotency_conflict_and_failed_transaction(self):
        actor = self.platform.account.id
        self.assertEqual(
            idempotent(actor, "test", "request-0001", {"a": 1}, lambda: {"ok": 1}), {"ok": 1}
        )
        self.assertEqual(
            idempotent(actor, "test", "request-0001", {"a": 1}, lambda: self.fail("重复执行")),
            {"ok": 1},
        )
        with self.assertRaisesMessage(BusinessError, "不同内容"):
            idempotent(actor, "test", "request-0001", {"a": 2}, lambda: {})

        def fail():
            Organization.objects.create(name="不应保存", kind="bank")
            raise BusinessError("test", "测试失败")

        with self.assertRaises(BusinessError):
            idempotent(actor, "test", "request-0002", {}, fail)
        self.assertFalse(Organization.objects.filter(name="不应保存").exists())
        self.assertEqual(IdempotencyRecord.objects.count(), 1)

    def test_member_tabs_and_pagination(self):
        response = api_client(self.resource).get(
            f"/api/v1/organizations/{self.resource.organization.id}/members?status=active&page_size=1"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 2)
        self.assertEqual(len(response.json()["results"]), 1)
        self.assertEqual(response.json()["counts"], {"active": 2, "disabled": 0, "all": 2})


class ConcurrencyTests(TransactionTestCase):
    def test_same_idempotency_key_executes_once(self):
        actor_id = uuid.uuid4()

        def run():
            close_old_connections()
            try:

                def create():
                    org = Organization.objects.create(name="并发合成", kind="bank")
                    return {"id": str(org.id)}

                return idempotent(actor_id, "concurrent", "request-0001", {}, create)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: run(), range(4)))
        self.assertTrue(all(result == results[0] for result in results))
        self.assertEqual(Organization.objects.count(), 1)
        self.assertEqual(IdempotencyRecord.objects.count(), 1)

    def test_simultaneous_admin_demotion_preserves_one(self):
        platform = actor_fixture()
        org = Organization.objects.create(name="并发机构", kind="bank")
        a = actor_fixture("bank", "13900000021", org=org)
        b = actor_fixture("bank", "13900000022", org=org)

        def run(member_id):
            close_old_connections()
            try:
                update_member(
                    platform, member_id, role="staff", active=True, version=1, reason="并发测试"
                )
                return "ok"
            except BusinessError as exc:
                return exc.code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(run, [a.membership.id, b.membership.id]))
        self.assertCountEqual(results, ["ok", "last_admin"])
        self.assertEqual(Membership.objects.filter(organization=org, role="admin").count(), 1)
