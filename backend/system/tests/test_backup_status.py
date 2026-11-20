from datetime import timedelta

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from system.models import OpsRun

URL = "/api/system/storage-status/"
pytestmark = pytest.mark.django_db


def record(*args, ago=None, **options):
    call_command("record_ops_run", *args, **options)
    run = OpsRun.objects.first()
    if ago is not None:
        run.finished_at = timezone.now() - ago
        run.save()
    return run


def status(api, ops):
    return api(ops).get(URL).json()


def test_fresh_install_has_no_backup_and_needs_attention(api, ops):
    data = status(api, ops)
    assert data["backup"] == {"last_ok": None, "last_failure": None, "overdue": True, "failing": False}
    assert data["drill"] == {"last": None, "overdue": False}  # nothing to drill before the first backup
    assert data["attention"] is True


def test_good_backup_clears_attention_and_overdue_comes_back(api, ops):
    run = record("backup", "ok", snapshot="abcdef12", detail="标签 daily")
    data = status(api, ops)
    assert data["backup"]["last_ok"]["snapshot"] == "abcdef12"
    assert data["backup"]["last_ok"]["detail"] == "标签 daily"
    assert data["attention"] is False
    run.finished_at = timezone.now() - timedelta(hours=27)
    run.save()
    data = status(api, ops)
    assert data["backup"]["overdue"] is True and data["attention"] is True


def test_failure_after_success_is_failing_until_the_next_success(api, ops):
    record("backup", "ok", snapshot="abcdef12", ago=timedelta(hours=2))
    record("backup", "failed", detail="导出数据库失败", ago=timedelta(hours=1))
    data = status(api, ops)
    assert data["backup"]["failing"] is True and data["backup"]["overdue"] is False
    assert data["backup"]["last_failure"]["detail"] == "导出数据库失败"
    assert data["attention"] is True
    record("backup", "ok", snapshot="bcdef123")
    data = status(api, ops)
    assert data["backup"]["failing"] is False and data["attention"] is False
    assert data["backup"]["last_failure"]["detail"] == "导出数据库失败"  # still shown, as history


def test_drill_due_a_month_after_first_backup_or_last_good_drill(api, ops):
    record("backup", "ok", snapshot="abcdef12", ago=timedelta(days=36))
    record("backup", "ok", snapshot="bcdef123")
    assert status(api, ops)["drill"]["overdue"] is True
    record("drill", "ok", snapshot="abcdef12", detail="附件校验 3 项")
    data = status(api, ops)
    assert data["drill"]["overdue"] is False and data["drill"]["last"]["detail"] == "附件校验 3 项"
    assert data["attention"] is False
    record("drill", "failed", detail="退出码 1")
    assert status(api, ops)["attention"] is True


def test_command_validates_and_keeps_the_newest_per_kind(settings):
    with pytest.raises(CommandError):
        call_command("record_ops_run", "backup", "ok", snapshot="not-hex")
    with pytest.raises(CommandError):
        call_command("record_ops_run", "restore", "ok")
    call_command("record_ops_run", "drill", "ok")
    for i in range(201):
        call_command("record_ops_run", "backup", "ok" if i else "failed", detail="x" * 300)
    assert OpsRun.objects.filter(kind="backup").count() == 200
    assert not OpsRun.objects.filter(kind="backup", ok=False).exists()  # the oldest went first
    assert OpsRun.objects.filter(kind="drill").count() == 1
    assert len(OpsRun.objects.first().detail) == 200


def test_only_ops_can_read(api, manager):
    assert api(manager).get(URL).status_code == 403
