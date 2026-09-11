import hashlib
import re
import threading
import time

from django.conf import settings

from chihuitong.crypto import normalize_phone
from chihuitong.errors import require

from .safe_json import request_json

_token_cache = {}
_token_lock = threading.Lock()


class WeChatMini:
    def __init__(self, audience):
        require(audience in {"customer", "clinic"}, "invalid_audience", "登录入口不合法", 400)
        config = settings.MINI_PROGRAMS[audience]
        self.appid, self.secret = config.get("appid", ""), config.get("secret", "")
        require(re.fullmatch(r"wx[a-fA-F0-9]{16}", self.appid or "") and isinstance(self.secret, str) and len(self.secret) >= 16, "mini_not_configured", "此小程序的服务端授权尚未配置", 503)
        other = settings.MINI_PROGRAMS["clinic" if audience == "customer" else "customer"].get("appid")
        require(not other or other != self.appid, "mini_app_conflict", "客户端与门诊端须配置不同AppID", 503)

    def check(self, result):
        code = result.get("errcode", 0)
        require(type(code) is int, "mini_response", "授权服务返回格式异常", 503)
        require(code == 0, "mini_authorization_failed", "微信授权未完成，请重新授权；持续失败请联系平台", 503 if code in {-1, 45009, 45011, 40164, 40125} else 400)
        return result

    def access_token(self):
        key = (self.appid, hashlib.sha256(self.secret.encode()).hexdigest())
        with _token_lock:
            cached = _token_cache.get(key)
            if cached and cached[1] > time.monotonic():
                return cached[0]
            result = self.check(request_json("api.weixin.qq.com", "/cgi-bin/stable_token", data={"grant_type": "client_credential", "appid": self.appid, "secret": self.secret, "force_refresh": False}))
            token, seconds = result.get("access_token"), result.get("expires_in")
            require(isinstance(token, str) and 1 <= len(token) <= 4096 and type(seconds) is int and 0 < seconds <= 7200, "mini_token_response", "授权凭证服务返回格式异常", 503)
            _token_cache[key] = (token, time.monotonic() + max(0, seconds - 60))
            return token

    def verify(self, login_code, phone_code):
        result = self.check(request_json("api.weixin.qq.com", "/sns/jscode2session", query={"appid": self.appid, "secret": self.secret, "js_code": login_code, "grant_type": "authorization_code"}))
        openid = result.get("openid")
        require(isinstance(openid, str) and 10 <= len(openid) <= 128, "mini_response", "微信身份返回格式异常", 503)
        # Sending openid asks WeChat to verify that the phone code belongs to this login identity.
        result = self.check(request_json("api.weixin.qq.com", "/wxa/business/getuserphonenumber", query={"access_token": self.access_token()}, data={"code": phone_code, "openid": openid}))
        info = result.get("phone_info")
        require(isinstance(info, dict) and isinstance(info.get("watermark"), dict), "mini_response", "手机号授权数据格式异常", 503)
        stamp = info["watermark"].get("timestamp")
        require(info["watermark"].get("appid") == self.appid and type(stamp) is int and -30 <= time.time() - stamp <= 330, "mini_watermark", "手机号授权归属或有效期不符，请重新授权", 400)
        require(str(info.get("countryCode")) == "86", "unsupported_phone", "目前仅支持中国大陆手机号", 400)
        phone = normalize_phone(info.get("purePhoneNumber"))
        full_phone = info.get("phoneNumber")
        require(full_phone == "86" + phone or normalize_phone(full_phone) == phone, "mini_phone_mismatch", "授权手机号校验失败", 400)
        # session_key, unionid, access_token and raw responses never leave this boundary.
        return {"appid": self.appid, "openid": openid, "phone": phone}
