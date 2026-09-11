import secrets
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.test import APIClient

from chihuitong.crypto import digest
from chihuitong.models import Membership, Organization, Session
from chihuitong.services.common import Actor
from chihuitong.services.organizations import account_for


class MemorySMS:
    messages = []

    def send_login(self, phone, code):
        self.messages.append((phone, code))


@transaction.atomic
def actor_fixture(kind="platform", phone="13900000001", role="admin", org=None):
    org = org or Organization.objects.create(name=f"合成测试{kind}", kind=kind)
    account = account_for(phone, "合成测试人员")
    member = Membership.objects.create(organization=org, account=account, role=role)
    return Actor(member)


def api_client(actor):
    token = secrets.token_urlsafe(48)
    Session.objects.create(token_digest=digest(token, purpose="session"), account=actor.account, audience="web", expires_at=timezone.now() + timedelta(hours=1))
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}", HTTP_X_MEMBERSHIP_ID=str(actor.membership.id))
    return client
