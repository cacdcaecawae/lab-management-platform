from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Notification


class Command(BaseCommand):
    help = "清理已读超过 180 天的站内通知；不清理未读通知。"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        old = Notification.objects.filter(read_at__lt=timezone.now() - timedelta(days=180))
        if options["dry_run"]:
            self.stdout.write(f"预览：可清理 {old.count()} 条（未执行）")
        else:
            count, _ = old.delete()
            self.stdout.write(f"已清理 {count} 条已读通知")
