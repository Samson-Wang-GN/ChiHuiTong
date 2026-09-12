from django.core.management.base import BaseCommand

from chihuitong.errors import require
from chihuitong.integrations.simulated import require_simulation
from chihuitong.models import Membership, SmsTemplate
from chihuitong.services.common import Actor
from chihuitong.services.notifications import configure_template, seed_templates


class Command(BaseCommand):
    help = "Initialize unused SMS templates for explicit synthetic acceptance only"

    def handle(self, *args, **options):
        require_simulation()
        seed_templates()
        member = (
            Membership.objects.select_related("organization", "account")
            .filter(organization__kind="platform", role="admin", active=True)
            .order_by("created_at", "id")
            .first()
        )
        require(member is not None, "platform_required", "请先初始化验收平台账号", 409)
        actor = Actor(member)
        count = 0
        # Never overwrite templates already configured by an acceptance user.
        for item in SmsTemplate.objects.filter(
            status="disabled", provider_template_id="", sign_name="", version=1
        ):
            configure_template(
                actor,
                item.code,
                content=item.content,
                parameter_names=item.parameter_names,
                provider_template_id="0",
                sign_name="齿慧通模拟验收",
                status="active",
                version=item.version,
                reason="REQ-045合成验收初始化，不发送真实短信",
            )
            count += 1
        self.stdout.write(f"Initialized {count} unused synthetic SMS templates")
