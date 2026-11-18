import pytest
from rest_framework.test import APIClient

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
