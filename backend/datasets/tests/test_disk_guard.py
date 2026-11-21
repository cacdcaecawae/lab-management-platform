"""Uploads stop before the disk fills up (core.disk), and 系统管理 says so."""

import pytest

from datasets.models import DataFile

pytestmark = pytest.mark.django_db


def test_upload_refused_when_it_would_leave_too_little_free_space(settings, api, student_a, ops, dataset_a, upload):
    settings.MIN_FREE_DISK = 10**18  # more than any disk has
    r = upload(api(student_a), dataset_a, [("wave.csv", b"t,a\n0,1\n")])
    assert r.status_code == 507
    assert r.data == {"code": "insufficient_storage", "message": "服务器磁盘剩余空间不足，暂时不能上传，请联系运维"}
    assert not DataFile.objects.exists() and not list((settings.MEDIA_ROOT).rglob("*.*"))
    status = api(ops).get("/api/system/storage-status/").json()
    assert status["disk_low"] is True and status["attention"] is True and status["disk_free"] > 0

    settings.MIN_FREE_DISK = 0
    assert upload(api(student_a), dataset_a, [("wave.csv", b"t,a\n0,1\n")]).status_code == 201
    assert api(ops).get("/api/system/storage-status/").json()["disk_low"] is False
