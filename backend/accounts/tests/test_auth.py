from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from accounts.models import User
from conftest import PASSWORD, make_user

pytestmark = pytest.mark.django_db


def csrf_client():
    client = APIClient(enforce_csrf_checks=True)
    assert client.get("/api/auth/csrf/").status_code == 204
    return client


def login_body():
    return {"username": "s_a", "password": PASSWORD}


def test_login_me_logout_with_csrf(student_a):
    client = csrf_client()
    r = client.post("/api/auth/login/", login_body(), format="json", HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
    assert r.status_code == 200
    assert r.data["username"] == "s_a" and r.data["group"]["name"] == "超声检测课题组"
    assert client.get("/api/auth/me/").data["role"] == "student"
    # Django rotates the CSRF token on login.
    r = client.post("/api/auth/logout/", HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
    assert r.status_code == 204
    assert client.get("/api/auth/me/").status_code == 403


def test_post_without_csrf_token_is_rejected(student_a):
    r = csrf_client().post("/api/auth/login/", login_body(), format="json")
    assert r.status_code == 403


def test_wrong_password_returns_uniform_error(student_a):
    r = APIClient().post("/api/auth/login/", {"username": "s_a", "password": "nope"}, format="json")
    assert r.status_code == 403
    assert r.data == {"code": "invalid_credentials", "message": "用户名或密码错误"}


def test_inactive_user_cannot_login(student_a):
    student_a.is_active = False
    student_a.save()
    assert APIClient().post("/api/auth/login/", login_body(), format="json").status_code == 403


def test_anonymous_gets_403_on_business_api(db):
    r = APIClient().get("/api/auth/me/")
    assert r.status_code == 403 and r.data["code"] == "not_authenticated"


def test_initial_password_must_be_changed_before_using_api(group, api):
    user = make_user("new", group, must_change_password=True)
    client = api(user)
    assert client.get("/api/auth/me/").data["must_change_password"] is True
    r = client.get("/api/members/")
    assert r.status_code == 403 and r.data["code"] == "password_change_required"
    weak = client.post("/api/auth/password/", {"old_password": PASSWORD, "new_password": "123"}, format="json")
    assert weak.status_code == 400 and weak.data["code"] == "validation_error"
    wrong_old = client.post("/api/auth/password/", {"old_password": "x", "new_password": "Str0ng-and-new"}, format="json")
    assert wrong_old.status_code == 400 and "old_password" in wrong_old.data["errors"]
    ok = client.post("/api/auth/password/", {"old_password": PASSWORD, "new_password": "Str0ng-and-new"}, format="json")
    assert ok.status_code == 204
    user.refresh_from_db()
    assert not user.must_change_password and user.check_password("Str0ng-and-new")
    assert client.get("/api/auth/me/").status_code == 200  # session survives the password change


def test_admin_waits_for_the_initial_password_to_be_changed(ops):
    ops.must_change_password = True  # e.g. the one-time password printed by scripts/install.sh
    ops.save()
    client = APIClient()
    client.force_login(ops)
    r = client.get("/admin/")
    assert r.status_code == 302 and r["Location"].startswith("/admin/login/")
    ops.must_change_password = False
    ops.save()
    assert client.get("/admin/").status_code == 200


def test_person_updates_own_contact_details_only(api, student_a, group):
    client = api(student_a)
    body = {"email": "a@example.edu", "phone": "13800000000", "wechat": "a_ut", "research_direction": "导波",
            "name": "冒名", "username": "taken", "role": "manager"}
    r = client.patch("/api/auth/me/", body, format="json")
    assert r.status_code == 200
    assert [r.data[k] for k in ("email", "phone", "wechat", "research_direction")] == [
        "a@example.edu", "13800000000", "a_ut", "导波"]
    student_a.refresh_from_db()
    # name, login name and role stay as the managers set them
    assert (student_a.name, student_a.username, student_a.role) == ("s_a", "s_a", "student")  # make_user names them after the login
    r = client.patch("/api/auth/me/", {"email": "not-an-email"}, format="json")
    assert r.status_code == 400 and "email" in r.data["errors"]

    fresh = make_user("s_new", group, must_change_password=True)
    r = api(fresh).patch("/api/auth/me/", {"phone": "1"}, format="json")
    assert r.status_code == 403 and r.data["code"] == "password_change_required"


def test_person_changes_own_avatar(api, student_a, group, settings, django_capture_on_commit_callbacks):
    client = api(student_a)
    url = "/api/auth/me/avatar/"
    assert client.get("/api/auth/me/").data["avatar_url"] is None
    assert client.get(url).status_code == 404

    with django_capture_on_commit_callbacks(execute=True):
        r = client.post(url, {"file": SimpleUploadedFile("me.png", b"first")})
    assert r.status_code == 200 and r.data["avatar_url"].startswith(url + "?v=")
    first_url = r.data["avatar_url"]
    first = Path(settings.MEDIA_ROOT, User.objects.get(pk=student_a.pk).avatar.name)
    got = client.get(url)
    assert got.status_code == 200 and b"".join(got.streaming_content) == b"first"
    assert got["Content-Type"] == "image/png" and got["X-Content-Type-Options"] == "nosniff"
    assert got["Cache-Control"] == "private, max-age=86400"

    with django_capture_on_commit_callbacks(execute=True):
        r = client.post(url, {"file": SimpleUploadedFile("me.jpg", b"second")})
    assert r.status_code == 200 and r.data["avatar_url"] != first_url  # a new URL: the browser drops the cached one
    assert not first.exists()  # the replaced picture is gone
    assert b"".join(client.get(url).streaming_content) == b"second"

    # pictures only (an SVG could run script), at most 2 MB, and not before the initial password is changed
    assert client.post(url, {"file": SimpleUploadedFile("me.svg", b"<svg/>")}).status_code == 400
    assert client.post(url, {"file": SimpleUploadedFile("me.jpg", b"x" * (2 * 1024**2 + 1))}).status_code == 413
    fresh = make_user("s_new", group, must_change_password=True)
    r = api(fresh).post(url, {"file": SimpleUploadedFile("me.png", b"x")})
    assert r.status_code == 403 and r.data["code"] == "password_change_required"
