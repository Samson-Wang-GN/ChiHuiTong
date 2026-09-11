"""Fail-closed settings: secrets and runtime files never reside in source releases."""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured


def required(name):
    value = os.environ.get(name, "")
    if not value:
        raise ImproperlyConfigured(f"缺少必要环境变量：{name}")
    return value


BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = required("CHT_SECRET_KEY")
FIELD_KEYS = required("CHT_FIELD_KEYS").split(",")
PHONE_INDEX_KEY = required("CHT_PHONE_INDEX_KEY")
ENVIRONMENT = os.environ.get("CHT_ENVIRONMENT", "production")
if ENVIRONMENT not in {"production", "development", "test"}:
    raise ImproperlyConfigured("CHT_ENVIRONMENT不合法")
DEBUG = False
ALLOWED_HOSTS = required("CHT_ALLOWED_HOSTS").split(",")
if "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured("禁止通配ALLOWED_HOSTS")
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": required("CHT_DB_NAME"),
        "USER": required("CHT_DB_USER"),
        "PASSWORD": os.environ.get("CHT_DB_PASSWORD", ""),
        "HOST": required("CHT_DB_HOST"),
        "PORT": os.environ.get("CHT_DB_PORT", "55432"),
        "CONN_MAX_AGE": 0,
        "OPTIONS": {"connect_timeout": 5},
        "TEST": {"NAME": os.environ.get("CHT_TEST_DB_NAME", "test_chihuitong")},
    }
}
INSTALLED_APPS = ["django.contrib.contenttypes", "rest_framework", "chihuitong"]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "chihuitong.http.RequestContextMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
APPEND_SLASH = False
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_SSL_REDIRECT = ENVIRONMENT == "production"
SECURE_HSTS_SECONDS = 31536000 if ENVIRONMENT == "production" else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
X_FRAME_OPTIONS = "DENY"
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["chihuitong.identity.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "UNAUTHENTICATED_USER": None,
    "EXCEPTION_HANDLER": "chihuitong.http.exception_handler",
}
DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 512 * 1024
PRIVATE_STORAGE = Path(required("CHT_PRIVATE_STORAGE")).resolve()
if PRIVATE_STORAGE == BASE_DIR or BASE_DIR in PRIVATE_STORAGE.parents:
    raise ImproperlyConfigured("附件必须位于源码目录之外")
SMS_BACKEND = os.environ.get("CHT_SMS_BACKEND", "chihuitong.integrations.sms.DisabledSMS")
TENCENT_MAP_KEY = os.environ.get("CHT_TENCENT_MAP_KEY", "")
MINI_PROGRAMS = {
    audience: {
        key: os.environ.get(f"CHT_MINI_{audience.upper()}_{key.upper()}", "")
        for key in ["appid", "secret"]
    }
    for audience in ["customer", "clinic"]
}
TENCENT_SMS = {
    key: os.environ.get("CHT_TENCENT_SMS_" + key.upper(), "")
    for key in ["secret_id", "secret_key", "sdk_app_id", "region"]
}
OTP_SECONDS = 300
OTP_COOLDOWN_SECONDS = 60
OTP_MAX_ATTEMPTS = 5
SESSION_SECONDS = 8 * 60 * 60
WECHAT_PAY_ENABLED = os.environ.get("CHT_WECHAT_PAY_ENABLED", "false").lower() == "true"
WECHAT_PAY = {
    key: os.environ.get("CHT_WXPAY_" + key.upper(), "")
    for key in [
        "mchid",
        "appid",
        "certificate_serial",
        "private_key_path",
        "public_key_id",
        "public_keys",
        "api_v3_key",
        "notify_url",
    ]
}
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "WARNING"},
    # Do not emit Django exception bodies/SQL containing uploaded patient values.
    "loggers": {"django.request": {"handlers": [], "propagate": False}},
}
