import time
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from chihuitong.errors import BusinessError
from chihuitong.integrations import wechat_mini
from chihuitong.models import MiniIdentity, MiniSession
from chihuitong.services import appointments

from .support import actor_fixture, api_client
from .test_appointments import appointment_setup, confirmed_appointment
from .test_sales import approve, order_fixture

MINI_SETTINGS = {
    "customer": {"appid": "wx1111111111111111", "secret": "synthetic-customer-secret"},
    "clinic": {"appid": "wx2222222222222222", "secret": "synthetic-clinic-secret"},
}


def mini_client(audience, phone, *, openid=None, name=None):
    client = APIClient()
    body = {"login_code": "login-" + uuid.uuid4().hex, "phone_code": "phone-" + uuid.uuid4().hex}
    if name:
        body["name"] = name
    with patch(
        "chihuitong.integrations.wechat_mini.WeChatMini.verify",
        return_value={
            "appid": MINI_SETTINGS[audience]["appid"],
            "openid": openid or "openid-" + uuid.uuid4().hex,
            "phone": phone,
        },
    ):
        response = client.post(f"/api/v1/mini/{audience}/login", body, format="json")
    if response.status_code == 200:
        headers = {"HTTP_AUTHORIZATION": "Bearer " + response.data["token"]}
        if audience == "clinic" and len(response.data["memberships"]) == 1:
            headers["HTTP_X_MEMBERSHIP_ID"] = response.data["memberships"][0]["id"]
        client.credentials(**headers)
    return client, response


@override_settings(MINI_PROGRAMS=MINI_SETTINGS)
class MiniTests(TestCase):
    def setUp(self):
        appointment_setup(self)

    def test_phone_authorization_customer_and_clinic_audiences_are_separate(self):
        customer, response = mini_client("customer", self.customer.phone)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["has_pending_benefits"])
        self.assertNotIn("openid", str(response.data))
        self.assertEqual(customer.get("/api/v1/mini/customer/me").status_code, 200)
        self.assertEqual(customer.get("/api/v1/mini/clinic/me").status_code, 401)
        self.assertEqual(customer.get("/api/v1/auth/me").status_code, 401)
        self.assertEqual(
            api_client(self.clinic_actor).get("/api/v1/mini/clinic/me").status_code, 401
        )
        clinic, response = mini_client("clinic", self.clinic_actor.account.phone)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["memberships"][0]["role_label"], "管理员")
        self.assertEqual(clinic.get("/api/v1/mini/customer/me").status_code, 401)
        _, failed = mini_client("clinic", self.customer.phone)
        self.assertEqual(failed.status_code, 403)

    def test_employee_appointments_only_and_disabled_membership_immediate(self):
        employee = actor_fixture("clinic", "13900000771", "staff", self.clinic_actor.organization)
        client, response = mini_client("clinic", employee.account.phone)
        self.assertEqual(response.status_code, 200, response.data)
        token = response.data["token"]
        client.credentials(
            HTTP_AUTHORIZATION="Bearer " + token, HTTP_X_MEMBERSHIP_ID=str(employee.membership.id)
        )
        self.assertEqual(client.get("/api/v1/mini/clinic/appointments").status_code, 200)
        self.assertEqual(client.get("/api/v1/mini/clinic/bills").status_code, 403)
        self.assertEqual(
            client.get(
                f"/api/v1/mini/clinic/organizations/{self.clinic_actor.organization.id}/cooperation"
            ).status_code,
            403,
        )
        employee.membership.active = False
        employee.membership.save(update_fields=["active"])
        self.assertEqual(client.get("/api/v1/mini/clinic/me").status_code, 401)

    def test_unknown_customer_can_authorize_without_name_but_must_complete_before_booking(self):
        client, response = mini_client("customer", "13900000772")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["needs_profile_completion"])
        order = approve(self, order_fixture(self, physical=True))
        activated = client.post(
            "/api/v1/mini/customer/cards/activate",
            {"credential": order.cards.first().credential, "confirmed": True},
            format="json",
            HTTP_IDEMPOTENCY_KEY="activate-new-phone",
        )
        self.assertEqual(activated.status_code, 200, activated.data)
        booking = {
            "benefit_id": activated.data["id"],
            "clinic_id": str(self.clinic.id),
            "requested_at": self.scheduled.isoformat(),
        }
        result = client.post(
            "/api/v1/mini/customer/appointments",
            booking,
            format="json",
            HTTP_IDEMPOTENCY_KEY="incomplete-profile",
        )
        self.assertEqual(result.status_code, 400, result.data)
        result = client.post(
            "/api/v1/mini/customer/profile",
            {"name": "合成新客户", "age": 28},
            format="json",
            HTTP_IDEMPOTENCY_KEY="complete-profile",
        )
        self.assertEqual(result.status_code, 200, result.data)
        result = client.post(
            "/api/v1/mini/customer/appointments",
            booking,
            format="json",
            HTTP_IDEMPOTENCY_KEY="complete-booking",
        )
        self.assertEqual(result.status_code, 201, result.data)
        result = client.post(
            "/api/v1/mini/customer/profile",
            {"phone": "13900000000"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="cannot-change-phone",
        )
        self.assertEqual(result.status_code, 400)

    def test_own_benefits_rules_direct_booking_detail_qr_and_other_customer_denied(self):
        item = confirmed_appointment(self)
        client, response = mini_client("customer", self.customer.phone)
        listing = client.get("/api/v1/mini/customer/benefits")
        self.assertEqual(listing.status_code, 200, listing.data)
        self.assertIn("usage_rules", listing.data["results"][0])
        self.assertNotIn("internal_name", listing.data["results"][0])
        detail = client.get(f"/api/v1/mini/customer/appointments/{item.id}")
        self.assertEqual(detail.data["redemption_qr"], self.card.credential)
        other, _ = mini_client("customer", "13900000773", name="合成其他客户")
        self.assertEqual(
            other.get(f"/api/v1/mini/customer/appointments/{item.id}").status_code, 404
        )
        denied = other.post(
            f"/api/v1/mini/customer/cards/{self.card.id}/claim",
            {"confirmed": True},
            format="json",
            HTTP_IDEMPOTENCY_KEY="cross-customer-claim",
        )
        self.assertEqual(denied.status_code, 404)

    def test_72_hour_message_read_not_restore_then_customer_absence_releases(self):
        item = confirmed_appointment(self)
        with patch("django.utils.timezone.now", return_value=self.scheduled + timedelta(hours=73)):
            appointments.process_deadline(item.id)
            client, _ = mini_client("customer", self.customer.phone)
            result = client.get("/api/v1/mini/customer/messages")
            self.assertEqual(result.status_code, 200, result.data)
            message_id = result.data["results"][0]["id"]
            client.post(f"/api/v1/mini/customer/messages/{message_id}/read", {}, format="json")
            item.refresh_from_db()
            self.assertEqual(item.status, "completed")
            self.assertTrue(item.reserved)
            response = client.post(
                f"/api/v1/mini/customer/appointments/{item.id}/feedback",
                {"arrived": False, "confirmed": True, "version": item.version},
                format="json",
                HTTP_IDEMPOTENCY_KEY="not-arrived-restore",
            )
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(response.data["status"], "cancelled")
            self.benefit.refresh_from_db()
            self.assertEqual(self.benefit.available, 1)

    def test_replay_and_identity_phone_change_fail_and_logout_revokes(self):
        client = APIClient()
        body = {"login_code": "unique-login-code", "phone_code": "unique-phone-code"}
        verified = {
            "appid": MINI_SETTINGS["customer"]["appid"],
            "openid": "same-wechat-identity",
            "phone": self.customer.phone,
        }
        with patch(
            "chihuitong.integrations.wechat_mini.WeChatMini.verify", return_value=verified
        ) as provider:
            first = client.post("/api/v1/mini/customer/login", body, format="json")
            second = client.post("/api/v1/mini/customer/login", body, format="json")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(provider.call_count, 1)
        _, changed = mini_client(
            "customer", "13900000774", openid="same-wechat-identity", name="合成用户"
        )
        self.assertEqual(changed.status_code, 409)
        client.credentials(HTTP_AUTHORIZATION="Bearer " + first.data["token"])
        self.assertEqual(
            client.post("/api/v1/mini/customer/logout", {}, format="json").status_code, 200
        )
        self.assertEqual(client.get("/api/v1/mini/customer/me").status_code, 401)
        self.assertIsNotNone(MiniSession.objects.first().revoked_at)
        self.assertEqual(MiniIdentity.objects.count(), 1)

    def test_mini_workbench_and_cooperation_links_stay_in_clinic_audience(self):
        appointments.book(
            self.customer.id,
            benefit_id=self.benefit.id,
            clinic_id=self.clinic.id,
            requested_at=self.scheduled,
        )
        client, response = mini_client("clinic", self.clinic_actor.account.phone)
        self.assertEqual(response.status_code, 200)
        board = client.get("/api/v1/mini/clinic/workbench")
        self.assertEqual(board.status_code, 200, board.data)
        self.assertTrue(board.data["task_endpoint"].startswith("/api/v1/mini/clinic/"))
        for task in board.data["tasks"]["results"]:
            self.assertEqual(client.get(task["detail_endpoint"]).status_code, 200)
        cooperation = client.get(
            f"/api/v1/mini/clinic/organizations/{self.clinic_actor.organization.id}/cooperation"
        )
        self.assertEqual(cooperation.status_code, 200, cooperation.data)
        for key in ["history_endpoint", "products_endpoint"]:
            self.assertTrue(cooperation.data[key].startswith("/api/v1/mini/clinic/"))
            self.assertEqual(client.get(cooperation.data[key]).status_code, 200)

    def test_customer_audit_scoped_context_and_idempotent_no_sensitive_payload(self):
        from chihuitong.models import AuditEvent
        from chihuitong.services.common import audit

        client, _ = mini_client("customer", self.customer.phone)
        data = {"name": "合成更新姓名", "occupation": "合成职业"}
        for _ in range(2):
            response = client.post(
                "/api/v1/mini/customer/profile",
                data,
                format="json",
                HTTP_IDEMPOTENCY_KEY="audit-profile-once",
            )
            self.assertEqual(response.status_code, 200, response.data)
        events = AuditEvent.objects.filter(object_id=self.customer.id, action="customer.profile")
        self.assertEqual(events.count(), 1)
        self.assertEqual(events.get().actor_role, "customer")
        self.assertNotIn("合成职业", str(events.get().metadata))
        system = audit(None, self.customer, "synthetic.system")
        self.assertEqual(system.actor_role, "")


@override_settings(MINI_PROGRAMS=MINI_SETTINGS)
class MiniPaymentTests(TestCase):
    from .test_finance import FinanceTests

    setUp = FinanceTests.setUp

    def test_jsapi_uses_verified_identity_not_request_openid(self):
        from types import SimpleNamespace
        from unittest.mock import Mock

        gateway = SimpleNamespace(
            config=SimpleNamespace(appid=MINI_SETTINGS["clinic"]["appid"], mchid="1900000001"),
            create=Mock(return_value={"prepay_id": "synthetic-prepay"}),
            client_parameters=Mock(return_value={"package": "prepay_id=synthetic-prepay"}),
        )
        client, response = mini_client(
            "clinic", self.clinic_actor.account.phone, openid="verified-clinic-openid"
        )
        self.assertEqual(response.status_code, 200, response.data)
        url = f"/api/v1/mini/clinic/bills/{self.bill.id}/payment"
        with patch("chihuitong.services.payments.WeChatPay", return_value=gateway):
            bad = client.post(
                url,
                {"version": self.bill.version, "openid": "forged"},
                format="json",
                HTTP_IDEMPOTENCY_KEY="cannot-forge-payer",
            )
            self.assertEqual(bad.status_code, 400)
            self.assertFalse(gateway.create.called)
            result = client.post(
                url,
                {"version": self.bill.version},
                format="json",
                HTTP_IDEMPOTENCY_KEY="verified-jsapi-payer",
            )
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(gateway.create.call_args.kwargs["openid"], "verified-clinic-openid")
        self.assertNotIn("verified-clinic-openid", str(result.data))
        self.assertEqual(result.data["method"], "jsapi")


@override_settings(MINI_PROGRAMS=MINI_SETTINGS)
class MiniGatewayTests(TestCase):
    def setUp(self):
        wechat_mini._token_cache.clear()

    def response(self):
        return {
            "errcode": 0,
            "phone_info": {
                "purePhoneNumber": "13900000988",
                "phoneNumber": "8613900000988",
                "countryCode": "86",
                "watermark": {
                    "appid": MINI_SETTINGS["customer"]["appid"],
                    "timestamp": int(time.time()),
                },
            },
        }

    def test_authorized_phone_is_bound_to_server_verified_openid_and_stable_token(self):
        with patch(
            "chihuitong.integrations.wechat_mini.request_json",
            side_effect=[
                {"openid": "verified-openid", "session_key": "discarded-secret"},
                {"access_token": "synthetic-access-token", "expires_in": 7200},
                self.response(),
            ],
        ) as remote:
            provider = wechat_mini.WeChatMini("customer")
            result = provider.verify("login-code", "phone-code")
            self.assertEqual(result["phone"], "13900000988")
            self.assertNotIn("session_key", result)
            self.assertEqual(
                remote.call_args_list[2].kwargs["data"],
                {"code": "phone-code", "openid": "verified-openid"},
            )
            self.assertFalse(remote.call_args_list[1].kwargs["data"]["force_refresh"])
            self.assertEqual(provider.access_token(), "synthetic-access-token")
            self.assertEqual(remote.call_count, 3)

    def test_wrong_app_stale_watermark_and_provider_rejection_fail_closed(self):
        for change in [{"appid": "wx3333333333333333"}, {"timestamp": int(time.time()) - 600}]:
            wechat_mini._token_cache.clear()
            response = self.response()
            response["phone_info"]["watermark"].update(change)
            with (
                patch(
                    "chihuitong.integrations.wechat_mini.request_json",
                    side_effect=[
                        {"openid": "verified-openid"},
                        {"access_token": "synthetic-token", "expires_in": 7200},
                        response,
                    ],
                ),
                self.assertRaises(BusinessError),
            ):
                wechat_mini.WeChatMini("customer").verify("login-code", "phone-code")
        with (
            patch(
                "chihuitong.integrations.wechat_mini.request_json",
                return_value={"errcode": 40029, "errmsg": "private-provider-response"},
            ),
            self.assertRaises(BusinessError) as result,
        ):
            wechat_mini.WeChatMini("customer").verify("login-code", "phone-code")
        self.assertNotIn("private-provider-response", str(result.exception))

    @override_settings(
        MINI_PROGRAMS={
            "customer": {"appid": "", "secret": ""},
            "clinic": {"appid": "", "secret": ""},
        }
    )
    def test_missing_configuration_does_not_invent_a_login(self):
        with self.assertRaises(BusinessError) as result:
            wechat_mini.WeChatMini("customer")
        self.assertEqual(result.exception.status, 503)
