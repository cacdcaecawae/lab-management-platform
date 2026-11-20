import re

from django.core.management.base import BaseCommand, CommandError

from system.models import OpsRun

KEEP = 200  # per kind


class Command(BaseCommand):
    help = "记录服务器上一次备份或恢复演练的结果（由 scripts/backup.sh、scripts/restore-drill.sh 调用）。"

    def add_arguments(self, parser):
        parser.add_argument("kind", choices=OpsRun.Kind.values)
        parser.add_argument("result", choices=["ok", "failed"])
        parser.add_argument("--snapshot", default="")
        parser.add_argument("--detail", default="")

    def handle(self, *args, kind, result, snapshot, detail, **options):
        if not re.fullmatch(r"[0-9a-f]{0,64}", snapshot):
            raise CommandError("快照编号应是十六进制")
        OpsRun.objects.create(kind=kind, ok=result == "ok", snapshot=snapshot, detail=detail[:200])
        old = list(OpsRun.objects.filter(kind=kind).values_list("pk", flat=True)[KEEP:])
        OpsRun.objects.filter(pk__in=old).delete()
