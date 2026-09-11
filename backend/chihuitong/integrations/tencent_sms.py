import hashlib
import hmac
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from django.conf import settings

from chihuitong.crypto import normalize_phone
from chihuitong.errors import BusinessError, require


def tc3_headers(secret_id, secret_key, region, payload, *, timestamp=None):
    stamp = int(time.time()) if timestamp is None else timestamp
    date = datetime.fromtimestamp(stamp, timezone.utc).strftime("%Y-%m-%d")
    host = "sms.tencentcloudapi.com"
    content_type = "application/json; charset=utf-8"
    headers = f"content-type:{content_type}\nhost:{host}\n"
    signed = "content-type;host"
    canonical = "POST\n/\n\n" + headers + "\n" + signed + "\n" + hashlib.sha256(payload).hexdigest()
    scope = date + "/sms/tc3_request"
    message = "TC3-HMAC-SHA256\n" + str(stamp) + "\n" + scope + "\n" + hashlib.sha256(canonical.encode()).hexdigest()
    key = ("TC3" + secret_key).encode()
    for value in [date, "sms", "tc3_request"]:
        key = hmac.new(key, value.encode(), hashlib.sha256).digest()
    signature = hmac.new(key, message.encode(), hashlib.sha256).hexdigest()
    return {"Content-Type": content_type, "Host": host, "X-TC-Action": "SendSms", "X-TC-Version": "2021-01-11",
            "X-TC-Timestamp": str(stamp), "X-TC-Region": region,
            "Authorization": f"TC3-HMAC-SHA256 Credential={secret_id}/{scope}, SignedHeaders={signed}, Signature={signature}"}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise BusinessError("sms_redirect", "短信服务地址异常", 503)


class TencentSMS:
    def send_login(self, phone, code):
        from chihuitong.models import SmsTemplate
        template = SmsTemplate.objects.filter(code="login", status="active").first()
        require(template, "sms_template_unavailable", "登录短信模板尚未配置", 503)
        self.send_template(phone, template, {"code": code, "minutes": "5"}, context="login")

    def send_template(self, phone, template, parameters, *, context):
        values = settings.TENCENT_SMS
        require(all(values.get(key) for key in ["secret_id", "secret_key", "sdk_app_id", "region"]),
                "sms_unavailable", "短信服务尚未配置", 503)
        require(template.status == "active" and template.provider_template_id and template.sign_name,
                "sms_template_unavailable", "短信模板尚未启用或报备", 503)
        phone = normalize_phone(phone)
        payload = {"PhoneNumberSet": ["+86" + phone], "SmsSdkAppId": values["sdk_app_id"],
                   "TemplateId": template.provider_template_id, "SignName": template.sign_name,
                   "TemplateParamSet": [str(parameters[key]) for key in template.parameter_names],
                   "SessionContext": context[:100]}
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        headers = tc3_headers(values["secret_id"], values["secret_key"], values["region"], raw)
        request = urllib.request.Request("https://sms.tencentcloudapi.com/", data=raw, headers=headers, method="POST")
        try:
            opener = urllib.request.build_opener(NoRedirect(), urllib.request.ProxyHandler({}))
            with opener.open(request, timeout=8) as response:
                raw_response = response.read(65537)
            require(len(raw_response) <= 65536, "sms_bad_response", "短信服务返回异常", 503)
            result = json.loads(raw_response)["Response"]
            require(not result.get("Error"), "sms_provider_error", "短信服务拒绝请求，请平台核查配置", 503)
            rows = result.get("SendStatusSet", [])
            require(len(rows) == 1 and rows[0].get("Code") == "Ok", "sms_send_rejected", "短信未被服务商接受", 503)
            require(normalize_phone(rows[0]["PhoneNumber"]) == phone, "sms_response_mismatch", "短信响应号码不匹配", 503)
            serial = rows[0].get("SerialNo", "")
            require(isinstance(serial, str) and re.fullmatch(r"[A-Za-z0-9_:-]{1,160}", serial),
                    "sms_bad_response", "短信服务未返回有效发送记录", 503)
            return serial
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise BusinessError("sms_network_unknown", "短信发送结果未确定，将稍后重试", 503) from exc
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            raise BusinessError("sms_bad_response", "短信服务响应不合法", 503) from exc
