from django.core.management.base import BaseCommand

from chihuitong.services.jobs import run_one
from chihuitong.services.scheduler import tick


class Command(BaseCommand):
    help = "单轮调度并处理发件箱；由独立服务每分钟调用，不访问共享队列"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--no-tick", action="store_true")

    def handle(self, *args, **options):
        limit = options["limit"]
        if limit < 1 or limit > 10000:
            from django.core.management.base import CommandError

            raise CommandError("单轮数量须在1～10000之间")
        if not options["no_tick"]:
            result = tick()
            self.stdout.write(f"queued={result['queued']}")
        count = 0
        while count < limit and run_one():
            count += 1
        self.stdout.write(f"processed={count}")
