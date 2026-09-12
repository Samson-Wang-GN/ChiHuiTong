import io
import json
from unittest.mock import patch

from django.test import TestCase, override_settings
from PIL import Image

from chihuitong.errors import BusinessError
from chihuitong.integrations import safe_json, tencent_map
from chihuitong.services import clinics, customers

from .support import actor_fixture, api_client
from .test_appointments import appointment_setup


class LocationTests(TestCase):
    def setUp(self):
        appointment_setup(self)
        self.address = {
            "province": "北京市",
            "city": "北京市",
            "district": "海淀区",
            "address": "合成测试路1号",
        }

    @override_settings(TENCENT_MAP_KEY="synthetic-map-key")
    def test_static_map_is_raster_only_scoped_and_bounded(self):
        stream = io.BytesIO()
        Image.new("RGB", (600, 360), "white").save(stream, format="PNG")
        data = {
            "clinic_id": str(self.clinic.id),
            "latitude": "39.900000",
            "longitude": "116.300000",
            "zoom": 17,
        }
        with patch(
            "urllib.request.OpenerDirector.open", return_value=io.BytesIO(stream.getvalue())
        ) as call:
            response = api_client(self.channel).post("/api/v1/clinics/map-preview", data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertTrue(
            call.call_args.args[0].full_url.startswith("https://apis.map.qq.com/ws/staticmap/v2/?")
        )
        self.assertNotIn("synthetic-map-key", response.content.decode("latin1"))
        self.assertEqual(
            api_client(self.resource).post("/api/v1/clinics/map-preview", data).status_code, 403
        )
        other = actor_fixture("channel", "13900000065")
        self.assertEqual(
            api_client(other).post("/api/v1/clinics/map-preview", data).status_code, 404
        )
        self.assertEqual(
            api_client(self.channel)
            .post("/api/v1/clinics/map-preview", {**data, "zoom": 99})
            .status_code,
            400,
        )
        for raw in [b'{"message":"secret-provider-body"}', b"x" * (2 * 1024 * 1024 + 1)]:
            with patch("urllib.request.OpenerDirector.open", return_value=io.BytesIO(raw)):
                response = api_client(self.channel).post("/api/v1/clinics/map-preview", data)
                self.assertEqual(response.status_code, 503)
                self.assertNotIn("secret-provider-body", str(response.data))

    @override_settings(TENCENT_MAP_KEY="synthetic-map-key")
    def test_candidate_gcj_precision_and_no_profile_mutation(self):
        payload = {
            "status": 0,
            "result": {"location": {"lng": 116.3, "lat": 39.9}, "level": 9, "reliability": 8},
        }
        with patch(
            "chihuitong.integrations.tencent_map.request_json", return_value=payload
        ) as request:
            response = api_client(self.channel).post(
                "/api/v1/clinics/geocode", {**self.address, "clinic_id": str(self.clinic.id)}
            )
        self.assertEqual(response.status_code, 200, response.data)
        candidate = response.data["candidate"]
        self.assertTrue(candidate["requires_map_confirmation"])
        self.assertEqual(candidate["coordinate_system"], "GCJ-02")
        self.assertEqual(candidate["status"], "unconfirmed")
        self.assertEqual(request.call_args.args[:2], ("apis.map.qq.com", "/ws/geocoder/v1/"))
        self.clinic.refresh_from_db()
        self.assertNotIn("location", self.clinic.profile)
        payload["result"]["level"] = 2
        with patch("chihuitong.integrations.tencent_map.request_json", return_value=payload):
            self.assertTrue(tencent_map.geocode("合成门诊地址")["needs_manual_adjustment"])

    @override_settings(TENCENT_MAP_KEY="")
    def test_missing_configuration_and_staff_scope(self):
        response = api_client(self.channel).post("/api/v1/clinics/geocode", self.address)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "map_not_configured")
        self.assertEqual(
            api_client(self.resource).post("/api/v1/clinics/geocode", self.address).status_code, 403
        )
        staff = actor_fixture("clinic", "13900000066", "staff", self.clinic_actor.organization)
        self.assertEqual(
            api_client(staff)
            .post("/api/v1/clinics/geocode", {**self.address, "clinic_id": str(self.clinic.id)})
            .status_code,
            403,
        )
        other = actor_fixture("channel", "13900000067")
        self.assertEqual(
            api_client(other)
            .post("/api/v1/clinics/geocode", {**self.address, "clinic_id": str(self.clinic.id)})
            .status_code,
            404,
        )

    def test_fixed_origin_transport_duplicate_json_and_no_error_body(self):
        with self.assertRaises(BusinessError):
            safe_json.request_json("127.0.0.1", "/")
        with patch(
            "urllib.request.OpenerDirector.open",
            return_value=io.BytesIO(b'{"status":0,"status":1}'),
        ):
            with self.assertRaises(BusinessError):
                safe_json.request_json("apis.map.qq.com", "/ws/geocoder/v1/")
        with patch(
            "urllib.request.OpenerDirector.open",
            return_value=io.BytesIO(json.dumps({"status": 0}).encode()),
        ) as call:
            safe_json.request_json(
                "apis.map.qq.com",
                "/ws/geocoder/v1/",
                query={"address": "合成地址&key=bad", "key": "synthetic"},
            )
            self.assertIn("%26key%3Dbad", call.call_args.args[0].full_url)
        with patch(
            "urllib.request.OpenerDirector.open", side_effect=TimeoutError("must not leak secret")
        ):
            with self.assertRaises(BusinessError) as failure:
                safe_json.request_json("apis.map.qq.com", "/ws/geocoder/v1/")
            self.assertNotIn("secret", str(failure.exception))

    def test_nested_untrusted_input_returns_business_error_and_external_zero_preserved(self):
        raw = {"name": "合成客户", "phone": "13900000198", "quantity": 1}
        self.assertEqual(
            customers.normalize_customer({**raw, "resource_customer_no": 0})[
                "resource_customer_no"
            ],
            "0",
        )
        for field, value in [
            ("gender", []),
            ("gender", {}),
            ("age", []),
            ("resource_customer_no", {}),
        ]:
            with self.subTest(field=field, value=value), self.assertRaises(BusinessError):
                customers.normalize_customer({**raw, field: value})
        with self.assertRaises(BusinessError):
            clinics.validate_profile(
                self.channel, {"responsible_id": []}, self.channel.organization, complete=False
            )
