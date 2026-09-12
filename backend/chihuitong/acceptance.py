"""Synthetic-data acceptance tools; never a production authentication alternative."""

import json
import os
import secrets
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, HttpResponse, JsonResponse
from django.utils import timezone
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .api import PhoneInput, validated
from .crypto import digest, normalize_phone, seal, unseal
from .errors import require
from .models import Account, LoginChallenge

ACCOUNTS = {
    "platform": ("13800000001", "平台管理员"),
    "resource": ("13800000002", "客户资源方管理员"),
    "channel": ("13800000003", "门诊渠道管理员"),
    "clinic": ("13800000004", "门诊管理员"),
}


def enabled():
    return settings.ACCEPTANCE_ENABLED and settings.ENVIRONMENT != "production"


class GateMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.ACCEPTANCE_ENABLED:
            provided = request.headers.get("X-CHT-Acceptance", "")
            if not enabled() or not secrets.compare_digest(
                provided, settings.ACCEPTANCE_PROXY_TOKEN
            ):
                return JsonResponse({"message": "验收入口访问未授权"}, status=403)
            # No cross-origin write or inbox reads, even on the same shared hostname.
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                origin = request.headers.get("Origin")
                expected = "https://" + request.get_host()
                if origin and origin != expected:
                    return JsonResponse({"message": "不允许跨站请求"}, status=403)
        return self.get_response(request)


def allowed(phone):
    require(enabled(), "disabled", "验收短信箱未启用", 404)
    phone = normalize_phone(phone)
    require(
        phone in {item[0] for item in ACCOUNTS.values()}
        or (
            settings.ACCEPTANCE_SIMULATED_EXTERNALS
            and Account.objects.filter(
                phone_index=digest(phone, purpose="phone"), active=True
            ).exists()
        ),
        "forbidden",
        "仅支持已开通的验收账号",
        403,
    )
    return phone


def mailbox_path(phone):
    return settings.PRIVATE_STORAGE / "acceptance-sms" / (digest(phone, purpose="phone") + ".enc")


class AcceptanceSMS:
    def send_login(self, phone, code):
        phone = allowed(phone)
        path = mailbox_path(phone)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = path.with_suffix("." + secrets.token_hex(8))
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as output:
            output.write(seal(code))
        os.replace(temporary, path)

    def send_template(self, phone, template, parameters, *, context):
        from .integrations.simulated import require_simulation

        require_simulation()
        # A synthetic reference is durable evidence of simulation, not SMS delivery.
        return "SIMULATED-" + str(context)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def inbox(request):
    phone = allowed(validated(PhoneInput, request)["phone"])
    challenge = LoginChallenge.objects.filter(phone_index=digest(phone, purpose="phone")).first()
    require(
        challenge
        and challenge.delivered
        and not challenge.consumed
        and challenge.expires_at > timezone.now()
        and challenge.attempts < settings.OTP_MAX_ATTEMPTS,
        "no_code",
        "请先获取验证码；旧验证码已使用、失效或过期",
        404,
    )
    path = mailbox_path(phone)
    require(path.is_file(), "no_code", "验证码尚未到达", 404)
    code = unseal(path.read_text())
    require(
        secrets.compare_digest(
            challenge.code_digest, digest(f"{challenge.phone_index}:{code}", purpose="otp")
        ),
        "no_code",
        "验证码已更新，请重新查看",
        404,
    )
    return Response({"code": code, "expires_at": challenge.expires_at, "synthetic_only": True})


def index(request, role=None):
    if not enabled() or (role is not None and role not in ACCOUNTS):
        return HttpResponse(status=404)
    root = Path(__file__).resolve().parent / "acceptance_assets"
    template = (root / "index.html").read_text(encoding="utf-8")
    return HttpResponse(template.replace("__ROLE__", json.dumps(role)), content_type="text/html")


def asset(request, name):
    if not enabled():
        return HttpResponse(status=404)
    if name in {
        "app.js",
        "style.css",
        "core.js",
        "catalog.js",
        "clinics.js",
        "workbench.js",
        "appointments.js",
        "finance.js",
        "operations.js",
        "sales.js",
        "imports.js",
        "overview.js",
        "reminder.js",
    }:
        path = Path(__file__).resolve().parent / "acceptance_assets" / name
    elif name in {"react.min.js", "react-dom.min.js", "arco.min.js", "arco.min.css"}:
        path = Path(__file__).resolve().parents[2] / "prototypes" / "shared" / "vendor" / name
    else:
        return HttpResponse(status=404)
    if not path.is_file():
        return HttpResponse(status=404)
    return FileResponse(
        path.open("rb"),
        content_type="text/css" if name.endswith(".css") else "application/javascript",
    )
