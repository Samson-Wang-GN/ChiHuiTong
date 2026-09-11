"""Encrypted values are never suitable for equality queries; use keyed blind indexes."""

import hashlib
import hmac
import json
import re
import unicodedata

from cryptography.fernet import Fernet, MultiFernet
from django.conf import settings
from django.db import models

from .errors import BusinessError


def cipher():
    return MultiFernet([Fernet(key.encode("ascii")) for key in settings.FIELD_KEYS])


def seal(value):
    return cipher().encrypt(value.encode("utf-8")).decode("ascii")


def unseal(value):
    return cipher().decrypt(value.encode("ascii")).decode("utf-8")


def digest(value, *, purpose):
    return hmac.new(
        settings.PHONE_INDEX_KEY.encode(), f"{purpose}:{value}".encode(), hashlib.sha256
    ).hexdigest()


def normalize_phone(value):
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        raise BusinessError("invalid_phone", "请输入有效的大陆手机号", 400)
    phone = unicodedata.normalize("NFKC", str(value)).strip()
    phone = re.sub(r"[\s\-()]", "", phone)
    for prefix in ("+86", "0086"):
        if phone.startswith(prefix):
            phone = phone[len(prefix) :]
            break
    if not re.fullmatch(r"1[3-9]\d{9}", phone):
        raise BusinessError("invalid_phone", "请输入有效的大陆手机号", 400)
    return phone


def masked_phone(value):
    return f"{value[:3]}****{value[-4:]}" if value else ""


class EncryptedTextField(models.TextField):
    def get_prep_value(self, value):
        return None if value is None else seal(str(value))

    def from_db_value(self, value, expression, connection):
        return None if value is None else unseal(value)


class EncryptedJSONField(EncryptedTextField):
    def get_prep_value(self, value):
        return None if value is None else seal(json.dumps(value, ensure_ascii=False))

    def from_db_value(self, value, expression, connection):
        return None if value is None else json.loads(unseal(value))
