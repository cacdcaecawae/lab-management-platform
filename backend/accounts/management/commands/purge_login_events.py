from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import LoginEvent


class Command(BaseCommand):
    help = "Delete login audit events older than 180 days (independent, idempotent maintenance)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Count expired records without deleting them.")

    def handle(self, *args, dry_run=False, **options):
        expired = LoginEvent.objects.filter(at__lt=timezone.now() - timedelta(days=180))
        if dry_run:
            self.stdout.write(f"Expired login events: {expired.count()}")
            return
        total = 0
        while ids := list(expired.order_by("pk").values_list("pk", flat=True)[:1000]):
            n, _ = expired.filter(pk__in=ids).delete()
            total += n
        self.stdout.write(f"Deleted login events: {total}")
