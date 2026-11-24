"""Managers manage student accounts (and their own profile); advisor and manager accounts are managed by ops in 系统管理."""

import pytest

from accounts.models import User
from conftest import PASSWORD, make_user

pytestmark = pytest.mark.django_db

NEW_PASSWORD = "Fresh-pass-2026"


def test_manager_cannot_touch_advisor_or_other_manager(api, group, manager, advisor):
    peer = make_user("mgr2", group, is_manager=True)  # another student with the 管理员 tag
    client = api(manager)
    for target in (advisor, peer):
        r = client.post(f"/api/members/{target.id}/reset-password/", {"password": NEW_PASSWORD}, format="json")
        assert r.status_code == 404
        assert client.patch(f"/api/members/{target.id}/", {"is_active": False}, format="json").status_code == 404
        assert client.get(f"/api/members/{target.id}/").status_code == 200  # still visible in the member list
        target.refresh_from_db()
        assert target.check_password(PASSWORD) and target.is_active


def test_manager_creates_students_only_and_hands_out_no_role_or_tag(api, manager, student_a):
    client = api(manager)
    grab = {"role": "advisor", "is_manager": True, "is_approver": True}
    body = {"username": "2026009", "name": "新导师", "password": NEW_PASSWORD, **grab}
    assert client.post("/api/members/", body, format="json").status_code == 201
    created = User.objects.get(username="2026009")
    assert (created.role, created.is_manager, created.is_approver) == ("student", False, False)
    assert client.patch(f"/api/members/{student_a.id}/", grab, format="json").status_code == 200
    student_a.refresh_from_db()
    assert (student_a.role, student_a.is_manager, student_a.is_approver) == ("student", False, False)


def test_manager_still_edits_own_profile(api, manager):
    r = api(manager).patch(f"/api/members/{manager.id}/", {"phone": "123"}, format="json")
    assert r.status_code == 200 and r.data["phone"] == "123"
