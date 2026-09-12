"""Explicit synthetic acceptance adapters. No transport or external credentials."""

from types import SimpleNamespace

from django.conf import settings
from django.utils import timezone

from chihuitong.errors import require

SIMULATED_MCHID = "SIMULATED-NO-MONEY"


def require_simulation():
    require(
        settings.ACCEPTANCE_ENABLED
        and settings.ACCEPTANCE_SIMULATED_EXTERNALS
        and settings.ENVIRONMENT != "production"
        and not settings.WECHAT_PAY_ENABLED,
        "simulation_disabled",
        "模拟外发仅允许独立合成验收环境使用",
        503,
    )


class SimulatedWeChatPay:
    def __init__(self):
        require_simulation()
        self.config = SimpleNamespace(appid="SIMULATED-APP", mchid=SIMULATED_MCHID)

    def create(self, attempt, *, openid=None):
        require_simulation()
        return {"simulated": True, "prepay_id": "SIMULATED-" + attempt.number}

    def client_parameters(self, prepay_id):
        require_simulation()
        return {"simulated": True, "message": "未调用微信，不能用于真实付款"}

    def query(self, number):
        require_simulation()
        from chihuitong.models import PaymentAttempt

        attempt = PaymentAttempt.objects.get(number=number, mchid=SIMULATED_MCHID)
        return {
            "appid": attempt.appid,
            "mchid": attempt.mchid,
            "out_trade_no": attempt.number,
            "amount": {"total": attempt.amount_cents, "currency": "CNY"},
            "trade_state": "SUCCESS",
            "trade_type": "NATIVE" if attempt.method == "native" else "JSAPI",
            "transaction_id": "SIMULATED-" + attempt.number,
            "success_time": timezone.now().isoformat(),
        }

    def close(self, number):
        require_simulation()
        return {"simulated": True}

    def notification(self, headers, raw):
        require(False, "simulation_callback_disabled", "模拟支付不接受外部回调", 403)
