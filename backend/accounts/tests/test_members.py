import pytest
from rest_framework.test import APIClient

from accounts.models import User
from conftest import PASSWORD, make_user

pytestmark = pytest.mark.django_db

NEW_PASSWORD = "Ultra-Sonic-2026"
PRIVATE = {"username", "email", "phone", "wechat", "must_change_password"}


def new_member(**extra):
    return {"username": "2026001", "name": "新同学", "role": "student", "email": "new@example.com",
            "password": NEW_PASSWORD, **extra}


def by_id(results):
    return {row["id"]: row for row in results}


def test_list_only_own_group(api, student_a, student_b, manager, advisor, other_manager):
    r = api(student_a).get("/api/members/")
    assert r.status_code == 200
    assert set(by_id(r.data["results"])) == {student_a.id, student_b.id, manager.id, advisor.id}


def test_student_sees_private_fields_only_for_self(api, student_a, student_b):
    rows = by_id(api(student_a).get("/api/members/").data["results"])
    assert PRIVATE <= set(rows[student_a.id])
    assert set(rows[student_b.id]) == {
        "id", "name", "role", "is_manager", "is_approver", "identity", "enrollment_year", "member_status", "tags",
        "research_direction", "is_active",
    }
    assert not PRIVATE & set(api(student_a).get(f"/api/members/{student_b.id}/").data)


@pytest.mark.parametrize("viewer", ["manager", "advisor"])
def test_supervisors_see_private_fields(api, request, student_a, viewer):
    r = api(request.getfixturevalue(viewer)).get(f"/api/members/{student_a.id}/")
    assert r.status_code == 200 and r.data["username"] == "s_a"


def test_other_group_member_is_404(api, student_a, other_manager):
    assert api(other_manager).get(f"/api/members/{student_a.id}/").status_code == 404
    assert api(student_a).get(f"/api/members/{other_manager.id}/").status_code == 404
    r = api(other_manager).patch(f"/api/members/{student_a.id}/", {"name": "x"}, format="json")
    assert r.status_code == 404


def test_search_and_filters(api, group, student_a, manager):
    make_user("2026999", group, name="王同学", research_direction="相控阵成像", is_active=False)
    client = api(manager)

    def names(query):
        return {row["name"] for row in client.get(f"/api/members/{query}").data["results"]}

    assert names("?search=相控阵") == {"王同学"}
    assert names("?search=2026999") == {"王同学"}
    assert names("?flag=manager") == {"mgr"}
    assert names("?role=manager") == set()  # no longer a role: the 管理员 tag
    assert names("?is_active=false") == {"王同学"}
    assert "王同学" not in names("?is_active=true")
    assert client.get("/api/members/?is_active=maybe").status_code == 400


def test_student_cannot_search_by_username(api, group, student_a):
    make_user("2026999", group, name="王同学")
    assert api(student_a).get("/api/members/?search=2026999").data["count"] == 0


def test_manager_creates_member_in_own_group(api, manager, group):
    r = api(manager).post("/api/members/", new_member(), format="json")
    assert r.status_code == 201
    assert r.data["username"] == "2026001" and r.data["must_change_password"] is True
    assert "password" not in r.data
    user = User.objects.get(username="2026001")
    assert user.group == group and user.check_password(NEW_PASSWORD)


def test_new_member_must_change_password_first(api, manager):
    api(manager).post("/api/members/", new_member(), format="json")
    client = APIClient()
    client.login(username="2026001", password=NEW_PASSWORD)
    r = client.get("/api/members/")
    assert r.status_code == 403 and r.data["code"] == "password_change_required"


def test_create_validates_password_and_required_fields(api, manager):
    r = api(manager).post("/api/members/", new_member(password="12345678"), format="json")
    assert r.status_code == 400 and "password" in r.data["errors"]
    r = api(manager).post("/api/members/", new_member(password="2026001x"), format="json")
    assert r.status_code == 400 and "password" in r.data["errors"]  # too similar to username
    r = api(manager).post("/api/members/", {"username": "x1", "password": NEW_PASSWORD}, format="json")
    assert r.status_code == 400 and "name" in r.data["errors"]


def test_create_duplicate_username_is_409(api, manager, other_manager):
    r = api(manager).post("/api/members/", new_member(username="other_mgr"), format="json")
    assert r.status_code == 409 and r.data["code"] == "conflict"


@pytest.mark.parametrize("writer", ["advisor", "student_a"])
def test_only_manager_can_write(api, request, student_b, writer):
    client = api(request.getfixturevalue(writer))
    assert client.post("/api/members/", new_member(), format="json").status_code == 403
    assert client.patch(f"/api/members/{student_b.id}/", {"name": "x"}, format="json").status_code == 403
    r = client.post(f"/api/members/{student_b.id}/reset-password/", {"password": NEW_PASSWORD}, format="json")
    assert r.status_code == 403


def test_manager_updates_member_but_not_group(api, manager, student_a, other_group):
    body = {"name": "陈同学", "role": "student", "phone": "123", "wechat": "chen_ut", "is_active": False, "group": other_group.id}
    r = api(manager).patch(f"/api/members/{student_a.id}/", body, format="json")
    assert r.status_code == 200
    student_a.refresh_from_db()
    assert (student_a.name, student_a.role, student_a.phone, student_a.wechat, student_a.is_active) == (
        "陈同学", "student", "123", "chen_ut", False)
    assert student_a.group_id != other_group.id


def test_manager_corrects_a_login_name(api, manager, student_a, student_b, other_manager):
    url = f"/api/members/{student_a.id}/"
    r = api(manager).patch(url, {"username": "2026017"}, format="json")
    assert r.status_code == 200 and r.data["username"] == "2026017"
    login = lambda name: APIClient().post("/api/auth/login/", {"username": name, "password": PASSWORD}, format="json").status_code
    assert (login("2026017"), login("s_a")) == (200, 403)  # the new name signs in, the old one no longer does
    # unchanged name is fine; taken by anyone (any group) -> 409; Django's username rules -> 400
    assert api(manager).patch(url, {"username": "2026017", "phone": "1"}, format="json").status_code == 200
    assert api(manager).patch(url, {"username": "s_b"}, format="json").status_code == 409
    assert api(manager).patch(url, {"username": "other_mgr"}, format="json").status_code == 409
    r = api(manager).patch(url, {"username": "2026 017"}, format="json")
    assert r.status_code == 400 and "username" in r.data["errors"]
    # still only students and their own account: not someone else's in another group
    assert api(manager).patch(f"/api/members/{other_manager.id}/", {"username": "x1"}, format="json").status_code == 404
    assert api(student_b).patch(f"/api/members/{student_b.id}/", {"username": "x2"}, format="json").status_code == 403


def test_manager_cannot_deactivate_self(api, manager):
    r = api(manager).patch(f"/api/members/{manager.id}/", {"is_active": False}, format="json")
    assert r.status_code == 400 and "is_active" in r.data["errors"]


def test_reset_password(api, manager, student_a):
    url = f"/api/members/{student_a.id}/reset-password/"
    assert api(manager).post(url, {"password": "123"}, format="json").status_code == 400
    assert api(manager).post(url, {"password": NEW_PASSWORD}, format="json").status_code == 204
    student_a.refresh_from_db()
    assert student_a.check_password(NEW_PASSWORD) and student_a.must_change_password


def test_no_delete_or_put(api, manager, student_a):
    url = f"/api/members/{student_a.id}/"
    assert api(manager).delete(url).status_code == 405
    assert api(student_a).delete(url).status_code == 405
    assert api(manager).put(url, {"name": "x"}, format="json").status_code == 405
