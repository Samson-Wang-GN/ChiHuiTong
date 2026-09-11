import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed

from .crypto import digest
from .errors import require
from .identity import rate_limit
from .integrations.wechat_mini import WeChatMini
from .models import Account, Benefit, Membership, MiniCodeUse, MiniIdentity, MiniSession
from .services.common import advisory_lock, audit
from .services.customers import register_verified_customer


def login(audience, *, login_code, phone_code, remote_address, name=None):
    rate_limit(f"mini-login:{remote_address}", seconds=3600, maximum=60)
    provider = WeChatMini(audience)
    require(
        all(isinstance(code, str) and 5 <= len(code) <= 512 for code in [login_code, phone_code]),
        "invalid_code",
        "请提供本次微信登录和手机号授权凭证",
        400,
    )
    # Commit consumption before outbound I/O; a retry requires fresh provider codes.
    with transaction.atomic():
        for kind, code in [("login", login_code), ("phone", phone_code)]:
            hashed = digest(f"{provider.appid}:{kind}:{code}", purpose="mini_code")
            advisory_lock("mini_code", hashed)
            _, created = MiniCodeUse.objects.get_or_create(digest=hashed)
            require(created, "code_used", "授权凭证已使用，请重新授权", 409)
    verified = provider.verify(login_code, phone_code)
    require(verified["appid"] == provider.appid, "mini_app_mismatch", "授权应用不一致", 400)
    with transaction.atomic():
        index = digest(verified["openid"], purpose="mini_openid")
        phone_index = digest(verified["phone"], purpose="phone")
        advisory_lock("mini_identity", provider.appid + index)
        identity = (
            MiniIdentity.objects.select_for_update()
            .filter(appid=provider.appid, openid_index=index)
            .first()
        )
        require(
            not identity or identity.audience == audience and identity.phone_index == phone_index,
            "phone_change_unsupported",
            "当前微信身份不支持更换绑定手机号，请联系平台",
            409,
        )
        customer = account = None
        if audience == "customer":
            customer = register_verified_customer(verified["phone"], name=name)
        else:
            account = Account.objects.filter(phone_index=phone_index, active=True).first()
            require(
                account
                and Membership.objects.filter(
                    account=account,
                    active=True,
                    organization__kind="clinic",
                    organization__status="active",
                ).exists(),
                "clinic_account_required",
                "此手机号未开通有效门诊账号，请联系门诊管理员；普通客户请使用客户端小程序",
                403,
            )
        if not identity:
            identity = MiniIdentity.objects.create(
                audience=audience,
                appid=provider.appid,
                openid_index=index,
                openid=verified["openid"],
                phone_index=phone_index,
                customer=customer,
                account=account,
            )
        require(
            identity.customer_id == (customer.id if customer else None)
            and identity.account_id == (account.id if account else None),
            "identity_conflict",
            "登录身份关联异常，请联系平台",
            403,
        )
        token = secrets.token_urlsafe(48)
        session = MiniSession.objects.create(
            identity=identity,
            token_digest=digest(token, purpose="mini_session"),
            expires_at=timezone.now() + timedelta(seconds=settings.SESSION_SECONDS),
        )
        audit(None, identity, "mini.login", audience=audience)
    return {"token": token, "expires_in": settings.SESSION_SECONDS, **session_profile(session)}


def session_profile(session):
    identity = session.identity
    if identity.audience == "customer":
        customer = identity.customer
        return {
            "audience": "customer",
            "customer_id": str(customer.id),
            "needs_profile_completion": not bool(customer.name),
            "has_pending_benefits": Benefit.objects.filter(
                customer=customer, pending__gt=0, card__frozen=False, card__order__status="issued"
            ).exists(),
        }
    return {
        "audience": "clinic",
        "account_id": str(identity.account_id),
        "memberships": [
            {
                "id": str(membership.id),
                "organization_id": str(membership.organization_id),
                "organization_name": membership.organization.name,
                "role": membership.role,
                "role_label": "管理员" if membership.role == "admin" else "员工",
            }
            for membership in Membership.objects.select_related("organization").filter(
                account_id=identity.account_id,
                active=True,
                organization__kind="clinic",
                organization__status="active",
            )
        ],
    }


def authenticate_mini(request, audience):
    header = request.headers.get("Authorization", "")
    if not header:
        return None
    parts = header.split()
    if len(parts) != 2 or parts[0] != "Bearer" or len(parts[1]) > 256:
        raise AuthenticationFailed("无效会话")
    session = (
        MiniSession.objects.select_related("identity__customer", "identity__account")
        .filter(
            token_digest=digest(parts[1], purpose="mini_session"),
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
            identity__audience=audience,
            identity__appid=settings.MINI_PROGRAMS[audience].get("appid", ""),
        )
        .first()
    )
    if not session:
        raise AuthenticationFailed("小程序会话已失效，请重新授权")
    identity = session.identity
    user = identity.customer if audience == "customer" else identity.account
    if not user or user.phone_index != identity.phone_index:
        raise AuthenticationFailed("身份绑定已失效")
    if audience == "customer" and user.registered_at is None:
        raise AuthenticationFailed("请先授权手机号")
    if audience == "clinic" and (
        not user.active
        or not Membership.objects.filter(
            account=user, active=True, organization__kind="clinic", organization__status="active"
        ).exists()
    ):
        raise AuthenticationFailed("门诊账号已停用")
    return user, session
