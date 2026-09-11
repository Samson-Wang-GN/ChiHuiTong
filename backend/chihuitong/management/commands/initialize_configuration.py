from django.core.management.base import BaseCommand

from chihuitong.services.notifications import seed_templates


class Command(BaseCommand):
    help = "初始化预置短信模板；不覆盖已有平台配置，不启用真实短信"

    def handle(self, *args, **options):
        seed_templates()
        self.stdout.write("预置配置已检查，已有配置保留。")
