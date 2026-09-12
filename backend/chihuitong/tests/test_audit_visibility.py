from django.test import TestCase

from chihuitong.api_audit import visible_metadata

from .support import actor_fixture


class AuditVisibilityTests(TestCase):
    def test_nested_allocation_fields_follow_role_visibility(self):
        data = {"fee_cents": 6000, "resource_cents": 1200, "channel_cents": 1800, "platform_cents": 3000}
        resource = actor_fixture("broker", "13900000321")
        channel = actor_fixture("channel", "13900000322")
        clinic = actor_fixture("clinic", "13900000323")
        self.assertEqual(visible_metadata(resource, {"history": [data]}), {"history": [{"resource_cents": 1200}]})
        self.assertEqual(visible_metadata(channel, data), {"fee_cents": 6000, "channel_cents": 1800})
        self.assertEqual(visible_metadata(clinic, data), {"fee_cents": 6000})
