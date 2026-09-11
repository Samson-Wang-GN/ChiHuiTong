import getpass

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from chihuitong.models import Membership, Organization
from chihuitong.services.common import advisory_lock, audit
from chihuitong.services.organizations import account_for


class Command(BaseCommand):
    help = "显式开通首个平台账号；交互读取手机号，不将其写入命令历史。"

    def handle(self, *args, **options):
        phone = getpass.getpass("平台管理员手机号（不回显）：")
        name = input("管理员姓名：").strip()
        with transaction.atomic():
            advisory_lock("bootstrap", "platform")
            if Organization.objects.filter(kind="platform").exists():
                raise CommandError("平台已初始化，请通过平台账号管理增设人员")
            org = Organization.objects.create(name="齿慧通平台", kind="platform")
            account = account_for(phone, name)
            member = Membership.objects.create(
                organization=org, account=account, role="admin", platform_created=True
            )
            audit(None, org, "platform.bootstrapped", initial_admin=str(member.id))
        self.stdout.write(self.style.SUCCESS("平台管理员已开通；配置短信服务后可登录。"))
