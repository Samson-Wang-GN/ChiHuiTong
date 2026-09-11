from django.db import models
from django.db.models import Q

from chihuitong.crypto import EncryptedTextField

from .core import Account, Entity
from .sales import Customer


class MiniIdentity(Entity):
    audience = models.CharField(max_length=16)
    appid = models.CharField(max_length=40)
    openid_index = models.CharField(max_length=64)
    openid = EncryptedTextField()
    phone_index = models.CharField(max_length=64)
    customer = models.ForeignKey(Customer, null=True, on_delete=models.PROTECT)
    account = models.ForeignKey(Account, null=True, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["appid", "openid_index"], name="mini_application_identity"),
            models.CheckConstraint(condition=Q(audience="customer", customer__isnull=False, account__isnull=True) | Q(audience="clinic", account__isnull=False, customer__isnull=True), name="mini_identity_audience_owner"),
        ]


class MiniSession(Entity):
    identity = models.ForeignKey(MiniIdentity, on_delete=models.PROTECT)
    token_digest = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True)

    @property
    def audience(self):
        return self.identity.audience


class MiniCodeUse(models.Model):
    digest = models.CharField(max_length=64, primary_key=True)
    used_at = models.DateTimeField(auto_now_add=True)
