import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.module_loading import import_string
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .crypto import digest, normalize_phone
from .errors import BusinessError, require
from .models import Account, LoginChallenge, Membership, RateBucket, Session
from .services.common import Actor, advisory_lock


def rate_limit(key, *, seconds, maximum):
    now = timezone.now()
    with transaction.atomic():
        hashed = digest(key, purpose="rate")
        advisory_lock("rate", hashed)
        bucket, _ = RateBucket.objects.get_or_create(key=hashed, defaults={"window": now})
        if now >= bucket.window + timedelta(seconds=seconds):
            bucket.window, bucket.count = now, 0
        require(bucket.count < maximum, "rate_limited", "操作过于频繁，请稍后重试", 429)
        bucket.count += 1
        bucket.save()


def request_code(phone, remote_address):
    phone = normalize_phone(phone)
    index = digest(phone, purpose="phone")
    rate_limit(f"otp-ip:{remote_address}", seconds=3600, maximum=30)
    rate_limit(f"otp-phone:{index}", seconds=3600, maximum=10)
    gateway = import_string(settings.SMS_BACKEND)()
    if settings.ENVIRONMENT == "production" and settings.SMS_BACKEND not in {
        "chihuitong.integrations.tencent_sms.TencentSMS", "chihuitong.integrations.sms.DisabledSMS"
    }:
        raise BusinessError("unsafe_sms_backend", "生产环境禁止测试短信服务", 503)
    now = timezone.now()
    code = f"{secrets.randbelow(1000000):06d}"
    code_hash = digest(f"{index}:{code}", purpose="otp")
    with transaction.atomic():
        advisory_lock("otp", index)
        old = LoginChallenge.objects.filter(phone_index=index).first()
        require(
            not old or now >= old.sent_at + timedelta(seconds=settings.OTP_COOLDOWN_SECONDS),
            "otp_cooldown",
            "请稍后重新获取验证码",
            429,
        )
        challenge, _ = LoginChallenge.objects.update_or_create(
            phone_index=index,
            defaults={
                "code_digest": code_hash,
                "expires_at": now + timedelta(seconds=settings.OTP_SECONDS),
                "sent_at": now,
                "attempts": 0,
                "consumed": False,
                "delivered": False,
            },
        )
    # Sending does not hold a database lock. A later replacement cannot be marked delivered.
    gateway.send_login(phone, code)
    LoginChallenge.objects.filter(pk=challenge.pk, code_digest=code_hash).update(delivered=True)
    return {"accepted": True, "expires_in": settings.OTP_SECONDS}


def verify_code(phone, code, remote_address):
    phone = normalize_phone(phone)
    index = digest(phone, purpose="phone")
    rate_limit(f"login-ip:{remote_address}", seconds=600, maximum=50)
    now = timezone.now()
    token = None
    with transaction.atomic():
        advisory_lock("otp", index)
        challenge = LoginChallenge.objects.select_for_update().filter(phone_index=index).first()
        valid = (
            challenge
            and challenge.delivered
            and not challenge.consumed
            and challenge.expires_at > now
            and challenge.attempts < settings.OTP_MAX_ATTEMPTS
        )
        if valid:
            challenge.attempts += 1
            matches = isinstance(code, str) and secrets.compare_digest(
                challenge.code_digest, digest(f"{index}:{code}", purpose="otp")
            )
            if matches:
                challenge.consumed = True
                account = Account.objects.filter(phone_index=index, active=True).first()
                if (
                    account
                    and Membership.objects.filter(
                        account=account, active=True, organization__status="active"
                    ).exists()
                ):
                    token = secrets.token_urlsafe(48)
                    Session.objects.create(
                        token_digest=digest(token, purpose="session"),
                        account=account,
                        audience="web",
                        expires_at=now + timedelta(seconds=settings.SESSION_SECONDS),
                    )
            challenge.save(update_fields=["attempts", "consumed"])
    # Failure is raised after committing attempts/consumption; failures cannot roll these back.
    require(token, "login_failed", "验证码无效、已过期或账号未开通，请重新核对", 401)
    return {"token": token, "expires_in": settings.SESSION_SECONDS, "audience": "web"}


class SessionAuthentication(BaseAuthentication):
    def authenticate(self, request):
        header = request.headers.get("Authorization", "")
        if not header:
            return None
        parts = header.split()
        if len(parts) != 2 or parts[0] != "Bearer" or len(parts[1]) > 256:
            raise AuthenticationFailed("无效会话")
        session = (
            Session.objects.select_related("account")
            .filter(
                token_digest=digest(parts[1], purpose="session"),
                revoked_at__isnull=True,
                expires_at__gt=timezone.now(),
                account__active=True,
                audience="web",
            )
            .first()
        )
        if not session:
            raise AuthenticationFailed("会话已失效，请重新登录")
        return session.account, session

    def authenticate_header(self, request):
        return "Bearer"


def request_actor(request):
    import uuid

    try:
        membership_id = uuid.UUID(request.headers.get("X-Membership-ID", ""))
    except (ValueError, TypeError, AttributeError) as exc:
        raise BusinessError("membership_required", "请选择有效的机构身份", 403) from exc
    membership = (
        Membership.objects.select_related("account", "organization")
        .filter(
            id=membership_id,
            account=request.user,
            active=True,
            organization__status="active",
            account__active=True,
        )
        .first()
    )
    require(membership, "forbidden", "无权使用该机构身份", 403)
    return Actor(membership, getattr(request, "request_id", None))
