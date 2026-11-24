"""Regression tests for the phase-1 security review (H1, M1, L3, L4, L6; M2 was replaced by dataset versions) and CSRF on logout / password change."""

import pytest
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from conftest import PASSWORD, make_user
from datasets.models import DataFile, Dataset

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("flag", ["is_superuser", "is_staff"])
def test_manager_cannot_take_over_ops_accounts(api, group, manager, flag):
    ops = make_user("ops", group, **{flag: True})
    client = api(manager)
    assert client.post(f"/api/members/{ops.id}/reset-password/", {"password": "Taken-Over-2026"}, format="json").status_code == 404
    assert client.patch(f"/api/members/{ops.id}/", {"is_active": False}, format="json").status_code == 404
    ops.refresh_from_db()
    assert ops.check_password(PASSWORD) and ops.is_active
    assert client.get(f"/api/members/{ops.id}/").status_code == 200  # still listed as a group member


def test_manager_cannot_change_own_role_or_tags(api, manager):
    r = api(manager).patch(f"/api/members/{manager.id}/", {"role": "advisor", "is_approver": True}, format="json")
    manager.refresh_from_db()
    assert r.status_code == 200 and (manager.role, manager.is_manager, manager.is_approver) == ("student", True, False)


@pytest.mark.parametrize("url", ["/api/members/?role=%00", "/api/projects/?status=%00", "/api/datasets/?kind=%00", "/api/datasets/?kind=nope"])
def test_invalid_choice_filters_return_empty_not_500(api, project, student_a, url):
    r = api(student_a).get(url)
    assert r.status_code == 200 and r.data["count"] == 0


def test_storage_write_failing_halfway_leaves_no_file(api, project, student_a, settings, monkeypatch):
    ds = Dataset.objects.create(owner=student_a, project=project, name="raw")
    original_save = FileSystemStorage._save

    def half_write(self, name, content):
        original_save(self, name, SimpleUploadedFile("part", b"partial"))  # bytes reach the disk...
        raise OSError("disk full")  # ...then the write fails

    monkeypatch.setattr(FileSystemStorage, "_save", half_write)
    with pytest.raises(OSError):
        api(student_a).post(f"/api/datasets/{ds.id}/files/", {"file": SimpleUploadedFile("a.txt", b"x")}, format="multipart")
    assert not DataFile.objects.exists()
    data_dir = settings.MEDIA_ROOT / "datasets"
    assert not any(p.is_file() for p in data_dir.rglob("*")) if data_dir.exists() else True


def test_user_without_group_cannot_use_business_api(api, db):
    loner = make_user("loner", None)
    r = api(loner).post("/api/reports/", {"week_start": "2026-11-16"}, format="json")
    assert r.status_code == 403 and r.data["code"] == "no_group"
    assert api(loner).get("/api/auth/me/").status_code == 200


def test_logout_and_password_change_require_csrf(student_a):
    client = APIClient(enforce_csrf_checks=True)
    client.force_login(student_a)
    assert client.post("/api/auth/logout/").status_code == 403
    body = {"old_password": PASSWORD, "new_password": "Str0ng-and-new"}
    assert client.post("/api/auth/password/", body, format="json").status_code == 403
    student_a.refresh_from_db()
    assert student_a.check_password(PASSWORD)
