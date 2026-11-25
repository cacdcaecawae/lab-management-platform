"""Regression tests for the phase-1 security review (H1, M1, L3, L4, L6; M2 was replaced by dataset versions) and CSRF on logout / password change."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from conftest import PASSWORD, make_user
from core.storage import CleanFileSystemStorage
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
    client = api(student_a)
    url = f"/api/datasets/{ds.pk}/files/"
    assert client.post(url, {"file": SimpleUploadedFile("first.txt", b"original")}, format="multipart").status_code == 201
    first = ds.files.get()
    monkeypatch.setattr(first.file.field, "generate_filename", lambda instance, name: first.file.name)
    original_save = CleanFileSystemStorage._save

    def fail_on_spare(self, name, content):
        assert name != first.file.name

        def broken_chunks():
            yield b"partial"
            raise OSError("disk full")

        monkeypatch.setattr(content, "chunks", broken_chunks)
        return original_save(self, name, content)

    monkeypatch.setattr(CleanFileSystemStorage, "_save", fail_on_spare)
    with pytest.raises(OSError, match="disk full"):
        client.post(url, {"file": SimpleUploadedFile("second.txt", b"x")}, format="multipart")
    assert list(DataFile.objects.values_list("pk", flat=True)) == [first.pk]
    assert [p for p in settings.MEDIA_ROOT.rglob("*") if p.is_file()] == [settings.MEDIA_ROOT / first.file.name]
    response = client.get(f"/api/files/{first.pk}/download/")
    assert b"".join(response.streaming_content) == b"original"


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
