from django.db import models
from django.utils import timezone


class OpsRun(models.Model):
    """How a backup or restore drill on the server ended. Written by `manage.py record_ops_run`, called from
    scripts/backup.sh and scripts/restore-drill.sh; a job that could not record at all shows up as overdue."""

    class Kind(models.TextChoices):
        BACKUP = "backup", "备份"
        DRILL = "drill", "恢复演练"

    kind = models.CharField(max_length=10, choices=Kind.choices)
    ok = models.BooleanField()
    finished_at = models.DateTimeField(default=timezone.now)
    snapshot = models.CharField(max_length=64, blank=True)
    detail = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-finished_at", "-id"]
