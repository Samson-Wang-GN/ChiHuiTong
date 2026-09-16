from django.db import models

from chihuitong.crypto import EncryptedJSONField, EncryptedTextField
from .core import Entity, Membership


class ContractTemplate(Entity):
    kind = models.CharField(max_length=16, choices=[("single", "单店"), ("chain", "连锁")])
    title = models.CharField(max_length=160)
    body = EncryptedTextField()
    platform_name = models.CharField(max_length=160)
    platform_credit_code = models.CharField(max_length=18)
    created_by = models.ForeignKey(Membership, on_delete=models.PROTECT)
    status = models.CharField(max_length=16, default="active")


class ContractPreparation(Entity):
    owner = models.ForeignKey(Membership, on_delete=models.PROTECT)
    kind = models.CharField(max_length=16, choices=[("single", "单店"), ("chain", "连锁")])
    number = models.CharField(max_length=80, unique=True)
    payload = EncryptedJSONField(default=dict)
    status = models.CharField(max_length=16, default="draft")
    generation = models.PositiveIntegerField(default=0)
    signed_ids = models.JSONField(default=list)
    signed_generation = models.PositiveIntegerField(default=0)
    agreement = models.OneToOneField("ClinicAgreement", null=True, on_delete=models.PROTECT)


class ContractPrint(Entity):
    preparation = models.ForeignKey(ContractPreparation, on_delete=models.PROTECT, related_name="prints")
    template = models.ForeignKey(ContractTemplate, on_delete=models.PROTECT)
    revision = models.PositiveIntegerField()
    snapshot = EncryptedJSONField()
    fingerprint = models.CharField(max_length=64)
    asset = models.OneToOneField("FileAsset", on_delete=models.PROTECT)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["preparation", "revision"], name="contract_print_revision")]
