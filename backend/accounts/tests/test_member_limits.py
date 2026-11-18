"""Managers manage student accounts (and their own profile); advisor and manager accounts are managed by ops in 系统管理."""

import pytest

from accounts.models import User
from conftest import PASSWORD, make_user

pytestmark = pytest.mark.django_db

NEW_PASSWORD = "Fresh-pass-2026"


def test_manager_cannot_touch_advisor_or_other_manager(api, group, manager, advisor):
    peer = make_user("mgr2", group, User.Role.MANAGER)
    client = api(manager)
    for target in (advisor, peer):
        r = client.post(f"/api/members/{target.id}/reset-password/", {"password": NEW_PASSWORD}, format="json")
        assert r.status_code == 404
        assert client.patch(f"/api/members/{target.id}/", {"is_active": False}, format="json").status_code == 404
        assert client.get(f"/api/members/{target.id}/").status_code == 200  # still visible in the member list
        target.refresh_from_db()
        assert target.check_password(PASSWORD) and target.is_active


def test_manager_creates_and_assigns_students_only(api, manager, student_a):
    client = api(manager)
    body = {"username": "2026009", "name": "新导师", "role": "advisor", "password": NEW_PASSWORD}
    r = client.post("/api/members/", body, format="json")
    assert r.status_code == 400 and "role" in r.data["errors"]
    r = client.patch(f"/api/members/{student_a.id}/", {"role": "manager"}, format="json")
    assert r.status_code == 400 and "role" in r.data["errors"]
    assert client.post("/api/members/", {**body, "role": "student"}, format="json").status_code == 201


def test_manager_still_edits_own_profile(api, manager):
    r = api(manager).patch(f"/api/members/{manager.id}/", {"phone": "123"}, format="json")
    assert r.status_code == 200 and r.data["phone"] == "123"
