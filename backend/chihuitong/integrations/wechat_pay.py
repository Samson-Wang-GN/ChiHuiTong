"""WeChat Pay APIv3 ordinary-merchant adapter. No mock or unsigned fallback."""

import base64
import binascii
import json
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings

from chihuitong.errors import BusinessError, require

MAX_MESSAGE = 1024 * 1024


def json_object(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate_key")
            result[key] = value
        return result

    try:
        require(
            isinstance(raw, bytes) and len(raw) <= MAX_MESSAGE,
            "wechat_message_size",
            "支付报文超出限制",
            400,
        )
        value = json.loads(raw, object_pairs_hook=unique)
        require(isinstance(value, dict), "wechat_message_shape", "支付报文结构不合法", 400)
        return value
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise BusinessError("wechat_invalid_json", "支付报文格式不合法", 400) from exc


@dataclass(frozen=True)
class PayConfiguration:
    mchid: str
    appid: str
    certificate_serial: str
    private_key: object
    public_key_id: str
    public_keys: dict
    api_v3_key: bytes
    notify_url: str


def load_configuration():
    require(
        settings.WECHAT_PAY_ENABLED,
        "wechat_not_configured",
        "微信支付尚未配置，请使用付款凭证方式",
        503,
    )
    values = settings.WECHAT_PAY
    required = [
        "mchid",
        "appid",
        "certificate_serial",
        "private_key_path",
        "public_key_id",
        "public_keys",
        "api_v3_key",
        "notify_url",
    ]
    require(
        all(values.get(key) for key in required), "wechat_not_configured", "微信支付配置不完整", 503
    )
    try:
        require(
            re.fullmatch(r"[0-9]{6,32}", values["mchid"])
            and re.fullmatch(r"[A-Za-z0-9]{6,32}", values["appid"])
            and re.fullmatch(r"[A-Fa-f0-9]{1,64}", values["certificate_serial"]),
            "wechat_invalid_config",
            "支付主体配置不合法",
            503,
        )
        url = urllib.parse.urlsplit(values["notify_url"])
        require(
            url.scheme == "https"
            and url.hostname
            and not url.username
            and not url.query
            and not url.fragment,
            "wechat_invalid_config",
            "支付回调必须是固定HTTPS地址",
            503,
        )
        configured_path = Path(values["private_key_path"])
        path = configured_path.resolve()
        require(
            configured_path.is_absolute() and not path.is_relative_to(settings.BASE_DIR.resolve()),
            "wechat_key_location",
            "商户私钥须使用源码目录外的绝对路径",
            503,
        )
        require(
            path.is_file() and path.stat().st_size <= 16384 and not (path.stat().st_mode & 0o077),
            "wechat_key_permissions",
            "商户私钥文件权限必须仅服务用户可读",
            503,
        )
        private = serialization.load_pem_private_key(path.read_bytes(), password=None)
        require(
            isinstance(private, rsa.RSAPrivateKey) and private.key_size >= 2048,
            "wechat_invalid_key",
            "商户签名密钥不合法",
            503,
        )
        configured = json.loads(values["public_keys"])
        require(
            isinstance(configured, dict) and 1 <= len(configured) <= 5,
            "wechat_invalid_key",
            "请配置可信微信公钥及轮换密钥",
            503,
        )
        keys = {}
        for serial, filename in configured.items():
            require(
                re.fullmatch(r"PUB_KEY_ID_[0-9]+", serial),
                "wechat_invalid_key",
                "微信公钥标识不合法",
                503,
            )
            key = serialization.load_pem_public_key(Path(filename).read_bytes())
            require(
                isinstance(key, rsa.RSAPublicKey) and key.key_size >= 2048,
                "wechat_invalid_key",
                "微信验签公钥不合法",
                503,
            )
            keys[serial] = key
        require(
            values["public_key_id"] in keys and len(values["api_v3_key"].encode()) == 32,
            "wechat_invalid_key",
            "微信验签或解密配置不完整",
            503,
        )
        return PayConfiguration(
            values["mchid"],
            values["appid"],
            values["certificate_serial"],
            private,
            values["public_key_id"],
            keys,
            values["api_v3_key"].encode(),
            values["notify_url"],
        )
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise BusinessError("wechat_invalid_config", "无法载入微信支付安全配置", 503) from exc


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise BusinessError("wechat_redirect_blocked", "支付服务返回非预期跳转，请查单核对", 503)


class WeChatPay:
    def __init__(self, configuration=None):
        self.config = configuration or load_configuration()

    def signature(self, message):
        return base64.b64encode(
            self.config.private_key.sign(message, padding.PKCS1v15(), hashes.SHA256())
        ).decode()

    def authorization(self, method, path, raw, *, timestamp=None, nonce=None):
        timestamp = str(timestamp if timestamp is not None else int(time.time()))
        nonce = nonce or secrets.token_hex(16)
        message = f"{method}\n{path}\n{timestamp}\n{nonce}\n".encode() + raw + b"\n"
        signature = self.signature(message)
        return (
            f'WECHATPAY2-SHA256-RSA2048 mchid="{self.config.mchid}",nonce_str="{nonce}",'
            f'signature="{signature}",timestamp="{timestamp}",serial_no="{self.config.certificate_serial}"'
        )

    def verify(self, headers, raw):
        headers = {key.lower(): value for key, value in headers.items()}
        try:
            stamp = headers["wechatpay-timestamp"]
            nonce = headers["wechatpay-nonce"]
            serial = headers["wechatpay-serial"]
            signature = headers["wechatpay-signature"]
            require(
                isinstance(stamp, str)
                and stamp.isdigit()
                and abs(int(stamp) - time.time()) <= 300
                and isinstance(nonce, str)
                and 1 <= len(nonce) <= 128
                and "\n" not in nonce
                and len(raw) <= MAX_MESSAGE,
                "wechat_signature_rejected",
                "支付签名已过期或格式无效",
                401,
            )
            key = self.config.public_keys.get(serial)
            require(key, "wechat_unknown_key", "未配置此微信验签公钥", 401)
            key.verify(
                base64.b64decode(signature, validate=True),
                f"{stamp}\n{nonce}\n".encode() + raw + b"\n",
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
        except (KeyError, TypeError, ValueError, binascii.Error, InvalidSignature) as exc:
            raise BusinessError("wechat_signature_rejected", "微信支付签名验证失败", 401) from exc

    def request(self, method, path, payload=None):
        require(
            method in {"GET", "POST"} and path.startswith("/v3/pay/transactions/"),
            "wechat_invalid_request",
            "支付请求不合法",
            500,
        )
        raw = (
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
            if payload is not None
            else b""
        )
        request = urllib.request.Request(
            "https://api.mch.weixin.qq.com" + path,
            data=raw if method == "POST" else None,
            method=method,
            headers={
                "Authorization": self.authorization(method, path, raw),
                "Wechatpay-Serial": self.config.public_key_id,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        # No redirect or environment proxy can forward payment credentials to another host.
        opener = urllib.request.build_opener(NoRedirect(), urllib.request.ProxyHandler({}))
        try:
            with opener.open(request, timeout=8) as response:
                body = response.read(MAX_MESSAGE + 1)
                self.verify(response.headers, body)
                return json_object(body) if body else {}
        except urllib.error.HTTPError as exc:
            exc.read(MAX_MESSAGE + 1)
            # Non-2xx responses are never authoritative transaction-state evidence.
            raise BusinessError(
                "wechat_remote_error", "微信支付请求未成功，请通过查单核实结果", 503
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise BusinessError(
                "wechat_network_unknown", "微信支付结果未确定，请稍后查单，不要重复付款", 503
            ) from exc

    def create(self, attempt, *, openid=None):
        require(attempt.method in {"native", "jsapi"}, "invalid_method", "支付方式不合法", 400)
        payload = {
            "appid": self.config.appid,
            "mchid": self.config.mchid,
            "description": "齿慧通门诊获客服务费",
            "out_trade_no": attempt.number,
            "notify_url": self.config.notify_url,
            "time_expire": attempt.expires_at.isoformat(timespec="seconds"),
            "amount": {"total": attempt.amount_cents, "currency": "CNY"},
        }
        if attempt.method == "jsapi":
            require(
                isinstance(openid, str) and 1 <= len(openid) <= 128,
                "openid_required",
                "请从门诊小程序登录后支付",
                403,
            )
            payload["payer"] = {"openid": openid}
        result = self.request("POST", f"/v3/pay/transactions/{attempt.method}", payload)
        key = "code_url" if attempt.method == "native" else "prepay_id"
        require(
            isinstance(result.get(key), str) and len(result[key]) <= 2048,
            "wechat_invalid_response",
            "微信下单结果不完整，请查单",
            503,
        )
        if attempt.method == "native":
            require(
                result[key].startswith("weixin://wxpay/"),
                "wechat_invalid_response",
                "支付二维码格式异常",
                503,
            )
        return {key: result[key]}

    def query(self, number):
        return self.request(
            "GET",
            "/v3/pay/transactions/out-trade-no/"
            + urllib.parse.quote(number, safe="")
            + "?"
            + urllib.parse.urlencode({"mchid": self.config.mchid}),
        )

    def close(self, number):
        self.request(
            "POST",
            "/v3/pay/transactions/out-trade-no/" + urllib.parse.quote(number, safe="") + "/close",
            {"mchid": self.config.mchid},
        )

    def client_parameters(self, prepay_id):
        timestamp, nonce = str(int(time.time())), secrets.token_hex(16)
        package = "prepay_id=" + prepay_id
        message = f"{self.config.appid}\n{timestamp}\n{nonce}\n{package}\n".encode()
        return {
            "appId": self.config.appid,
            "timeStamp": timestamp,
            "nonceStr": nonce,
            "package": package,
            "signType": "RSA",
            "paySign": self.signature(message),
        }

    def notification(self, headers, raw):
        self.verify(headers, raw)
        envelope = json_object(raw)
        try:
            require(
                envelope.get("event_type") == "TRANSACTION.SUCCESS"
                and envelope.get("resource_type") == "encrypt-resource"
                and isinstance(envelope.get("id"), str)
                and 1 <= len(envelope["id"]) <= 100,
                "wechat_invalid_event",
                "非预期支付通知",
                400,
            )
            resource = envelope["resource"]
            require(
                resource["algorithm"] == "AEAD_AES_256_GCM"
                and resource["original_type"] == "transaction",
                "wechat_invalid_algorithm",
                "支付通知加密方式不合法",
                400,
            )
            plaintext = AESGCM(self.config.api_v3_key).decrypt(
                resource["nonce"].encode(),
                base64.b64decode(resource["ciphertext"], validate=True),
                resource.get("associated_data", "").encode(),
            )
            return envelope["id"], json_object(plaintext)
        except (KeyError, TypeError, ValueError, AttributeError, binascii.Error, InvalidTag) as exc:
            raise BusinessError("wechat_decryption_failed", "微信支付通知解密失败", 400) from exc
