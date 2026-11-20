"""Read-only operational view; the web process cannot mount storage."""
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from core.nas_storage import nas_ready
from core.permissions import IsSuperuser

from .models import OpsRun

BACKUP_DUE = timedelta(hours=26)  # daily cron at 02:30 plus two hours of slack
DRILL_DUE = timedelta(days=35)  # handbook: one drill a month


def run(r):
    return r and {"finished_at": r.finished_at, "ok": r.ok, "snapshot": r.snapshot, "detail": r.detail}


def ops_status(now):
    backups = OpsRun.objects.filter(kind=OpsRun.Kind.BACKUP)
    last_ok, last_failure = backups.filter(ok=True).first(), backups.filter(ok=False).first()
    drills = OpsRun.objects.filter(kind=OpsRun.Kind.DRILL)
    last_drill = drills.first()
    # Due a month after the last good drill, or after the first backup if there has never been one.
    since = drills.filter(ok=True).first() or backups.filter(ok=True).last()
    backup = {
        "last_ok": run(last_ok),
        "last_failure": run(last_failure),
        "overdue": not last_ok or now - last_ok.finished_at > BACKUP_DUE,
        "failing": bool(last_failure) and (not last_ok or last_failure.finished_at > last_ok.finished_at),
    }
    drill = {"last": run(last_drill), "overdue": bool(since) and now - since.finished_at > DRILL_DUE}
    attention = backup["overdue"] or backup["failing"] or drill["overdue"] or bool(last_drill and not last_drill.ok)
    return backup, drill, attention


class StorageView(APIView):
    permission_classes = [IsSuperuser]

    def get(self, request):
        nas = bool(settings.LAB_NAS_STORAGE_ID)
        ready = nas_ready(settings.MEDIA_ROOT) if nas else None
        backup, drill, attention = ops_status(timezone.now())
        return Response({
            "primary": "nas" if nas else "local",
            "nas_ready": ready,
            "backup": backup,
            "drill": drill,
            "attention": attention or ready is False,
        })
