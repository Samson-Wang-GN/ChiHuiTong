from chihuitong.errors import BusinessError


class DisabledSMS:
    def send_login(self, phone, code):
        raise BusinessError("sms_unavailable", "短信服务尚未配置，请联系平台", 503)

    def send_template(self, phone, template, parameters, *, context):
        raise BusinessError("sms_unavailable", "短信服务尚未配置，请联系平台", 503)
