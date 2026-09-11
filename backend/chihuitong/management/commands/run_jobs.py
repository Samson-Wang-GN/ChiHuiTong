from django.core.management.base import BaseCommand

from chihuitong.services.jobs import run_one


class Command(BaseCommand):
    help = "领取并执行有限数量后台任务；失败保留状态和错误编号，后续可重试。"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        count = 0
        for _ in range(min(max(options["limit"], 1), 1000)):
            if not run_one():
                break
            count += 1
        self.stdout.write(f"已处理任务数量：{count}")
