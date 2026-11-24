"""Students register through their group's link and wait, inactive, until a manager of that group approves them."""

import threading

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import Collector
from rest_framework.test import APIClient

from accounts.member_serializers import RegisterSerializer
from accounts.models import User
from accounts.views import PENDING_LIMIT
from core.models import Notification

pytestmark = pytest.mark.django_db

SIGNUP = "/api/members/signup/"
PASSWORD = "Signup-2026-pass!"
ADDRESS = {"HTTP_X_FORWARDED_FOR": "10.0.0.9"}


def open_link(api, manager):
    r = api(manager).post(SIGNUP, {"open": True}, format="json")
    assert r.status_code == 200 and len(r.data["code"]) >= 12
    return r.data["code"]


def register(code, username="s_new", client=None, **extra):
    body = {"code": code, "username": username, "name": "新同学", "email": "new@example.edu", "password": PASSWORD, **extra}
    return (client or APIClient()).post("/api/auth/register/", body, format="json", **ADDRESS)


def login(username="s_new", password=PASSWORD):
    return APIClient().post("/api/auth/login/", {"username": username, "password": password}, format="json")


def test_register_waits_for_approval_then_logs_in_without_changing_password(api, manager, advisor, student_a):
    code = open_link(api, manager)
    assert register(code).status_code == 201
    user = User.objects.get(username="s_new")
    assert (user.group, user.role, user.is_active, user.pending, user.must_change_password) == (
        manager.group, User.Role.STUDENT, False, True, False)
    # The managers hear about it; nobody else does.
    assert list(Notification.objects.values_list("recipient__username", "link")) == [("mgr", "/members")]

    r = login()
    assert r.status_code == 403 and r.data["code"] == "pending_approval"
    assert login(password="wrong-pass").data["code"] == "invalid_credentials"  # no hint without the password

    pending = api(manager).get("/api/members/pending/").data
    assert [(p["username"], p["name"], p["email"]) for p in pending] == [("s_new", "新同学", "new@example.edu")]
    assert api(manager).post("/api/members/approve/", {"ids": [user.pk]}, format="json").data == {"count": 1}
    r = login()
    assert r.status_code == 200 and r.data["must_change_password"] is False
    assert api(manager).get("/api/members/pending/").data == []


def test_a_closed_rotated_or_wrong_link_rejects_before_looking_at_the_student_number(api, manager, student_a):
    old = open_link(api, manager)
    new = open_link(api, manager)  # "换一个"
    for code in (old, "", None, ["x"], "not-a-code"):
        r = register(code, username="s_a")  # s_a exists, but that must not show without a valid link
        assert r.status_code == 400 and list(r.data["errors"]) == ["code"], (code, r.data)
    assert register(new, username="s_a").status_code == 409
    assert api(manager).post(SIGNUP, {"open": False}, format="json").data == {"code": ""}
    assert register(new).status_code == 400
    assert api(manager).get(SIGNUP).data == {"code": ""}
    assert not User.objects.filter(username="s_new").exists()


def test_form_is_checked_like_a_new_account(api, manager):
    code = open_link(api, manager)
    assert list(register(code, name="").data["errors"]) == ["name"]
    assert list(register(code, password="123").data["errors"]) == ["password"]
    assert register(code, role="manager", is_active=True, pending=False, group=999).status_code == 201
    user = User.objects.get(username="s_new")
    assert (user.role, user.is_active, user.pending, user.group_id) == (User.Role.STUDENT, False, True, manager.group_id)


def test_registration_needs_csrf(api, manager):
    code = open_link(api, manager)
    r = register(code, client=APIClient(enforce_csrf_checks=True))
    assert r.status_code == 403 and not User.objects.filter(username="s_new").exists()


def test_applicants_are_not_members_until_approved(api, manager, student_a, project):
    code = open_link(api, manager)
    register(code)
    applicant = User.objects.get(username="s_new")
    for viewer in (manager, student_a):
        names = [m["name"] for m in api(viewer).get("/api/members/").data["results"]]
        assert "新同学" not in names
    assert api(manager).get(f"/api/members/{applicant.pk}/").status_code == 404
    assert api(manager).patch(f"/api/members/{applicant.pk}/", {"is_active": True}, format="json").status_code == 404
    # Pickers that also accept former members (achievements, meetings) must not accept applicants.
    r = api(student_a).post("/api/achievements/", {
        "type": "paper", "title": "t", "authors": "a", "venue": "v", "date": "2026-01-01", "status": "accepted",
        "member_ids": [student_a.pk, applicant.pk],
    }, format="json")
    assert r.status_code == 400 and "member_ids" in r.data["errors"]
    r = api(manager).patch(f"/api/projects/{project.pk}/", {"member_ids": [applicant.pk]}, format="json")
    assert r.status_code == 400


def test_only_this_groups_managers_decide_and_only_on_applicants(api, manager, student_a, other_manager):
    code = open_link(api, manager)
    register(code, username="s_x")
    register(code, username="s_y")
    register(code, username="s_z")
    x, y, z = (User.objects.get(username=u).pk for u in ("s_x", "s_y", "s_z"))
    # Another group's manager reaches nothing of this group.
    assert api(other_manager).get("/api/members/pending/").data == []
    assert api(other_manager).post("/api/members/approve/", {"ids": [x]}, format="json").data == {"count": 0}
    assert api(other_manager).post("/api/members/reject/", {"ids": [x]}, format="json").data == {"count": 0}

    # Active members and unknown IDs in the list are ignored.
    r = api(manager).post("/api/members/approve/", {"ids": [x, y, student_a.pk, 99999]}, format="json")
    assert r.data == {"count": 2}
    assert api(manager).post("/api/members/reject/", {"ids": [z, student_a.pk]}, format="json").data == {"count": 1}
    assert not User.objects.filter(pk=z).exists() and User.objects.filter(pk=student_a.pk, is_active=True).exists()
    assert register(code, username="s_z").status_code == 201  # a rejected student number may apply again
    assert api(manager).post("/api/members/approve/", {"ids": []}, format="json").status_code == 400


def test_outsiders_cannot_approve_or_open_links(api, manager, advisor, student_a):
    for outsider in (advisor, student_a):
        client = api(outsider)
        assert client.get("/api/members/pending/").status_code == 403
        assert client.post("/api/members/approve/", {"ids": [1]}, format="json").status_code == 403
        assert client.post("/api/members/reject/", {"ids": [1]}, format="json").status_code == 403
        assert client.get(SIGNUP).status_code == 403
        assert client.post(SIGNUP, {"open": True}, format="json").status_code == 403
    assert APIClient().get("/api/members/pending/").status_code == 403


def test_pending_cap_and_rate_limit(api, manager):
    code = open_link(api, manager)
    group = manager.group
    User.objects.bulk_create([
        User(username=f"p{i}", name="x", group=group, is_active=False, pending=True) for i in range(PENDING_LIMIT)
    ])
    r = register(code)
    assert r.status_code == 409 and r.data["code"] == "too_many_pending"
    User.objects.filter(pending=True).delete()
    # 10 an hour from one address, whatever happened to them (here: the cap was hit once already).
    assert [register(code, username=f"n{i}").status_code for i in range(9)] == [201] * 9
    assert register(code, username="n9").status_code == 429


def test_ops_sees_applicants_and_switching_one_on_approves_it(api, ops, manager):
    register(open_link(api, manager))
    applicant = User.objects.get(username="s_new")
    row = next(a for a in api(ops).get("/api/system/accounts/").data["results"] if a["username"] == "s_new")
    assert (row["is_active"], row["pending"]) == (False, True)
    assert api(ops).patch(f"/api/system/accounts/{applicant.pk}/", {"is_active": True}, format="json").status_code == 200
    applicant.refresh_from_db()
    assert (applicant.is_active, applicant.pending) == (True, False)


def test_an_applicant_is_always_an_inactive_student(api, ops, manager):
    code = open_link(api, manager)
    register(code)
    applicant = User.objects.get(username="s_new")
    # Ops makes the applicant an advisor: it is no longer an application the group's managers may approve or delete.
    assert api(ops).patch(f"/api/system/accounts/{applicant.pk}/", {"role": "advisor"}, format="json").status_code == 200
    applicant.refresh_from_db()
    assert (applicant.role, applicant.is_active, applicant.pending) == (User.Role.ADVISOR, False, False)
    assert api(manager).get("/api/members/pending/").data == []
    for decision in ("approve", "reject"):
        assert api(manager).post(f"/api/members/{decision}/", {"ids": [applicant.pk]}, format="json").data == {"count": 0}
    applicant.refresh_from_db()
    assert not applicant.is_active
    # Django admin saves through the model too: switching an applicant on approves it.
    register(code, username="s_admin")
    other = User.objects.get(username="s_admin")
    other.is_active = True
    other.save()
    other.refresh_from_db()
    assert not other.pending
    # And the database refuses a pending account that is active or not a student.
    for change in ({"is_active": True}, {"role": User.Role.ADVISOR}):
        with pytest.raises(IntegrityError), transaction.atomic():
            User.objects.filter(pk=applicant.pk).update(**{"pending": True, "role": User.Role.STUDENT, "is_active": False, **change})


@pytest.mark.django_db(transaction=True)
def test_approving_while_another_manager_rejects_never_deletes_an_approved_account(api, manager, monkeypatch):
    register(open_link(api, manager))
    applicant = User.objects.get(username="s_new")
    client, approved, workers = api(manager), {}, []
    original = Collector.delete

    def approve():
        try:
            approved["count"] = client.post("/api/members/approve/", {"ids": [applicant.pk]}, format="json").data["count"]
        finally:
            connection.close()

    def delete_after_an_approval(collector):
        if workers or User not in collector.data:  # e.g. the session a login replaces
            return original(collector)
        # The rows to delete are already read; the other manager approves before they go.
        workers.append(threading.Thread(target=approve))
        workers[0].start()
        workers[0].join(2)  # with the applicant locked, the approval waits for the rejection instead
        return original(collector)

    monkeypatch.setattr(Collector, "delete", delete_after_an_approval)
    rejected = api(manager).post("/api/members/reject/", {"ids": [applicant.pk]}, format="json").data["count"]
    workers[0].join(15)
    assert not workers[0].is_alive()
    kept = User.objects.filter(pk=applicant.pk, is_active=True, pending=False).exists()
    assert (approved["count"], rejected, kept) in [(1, 0, True), (0, 1, False)]


@pytest.mark.django_db(transaction=True)
def test_a_link_closed_during_a_registration_lets_nothing_in_after_it(api, manager, monkeypatch):
    code = open_link(api, manager)
    client, closed, workers, seen = api(manager), threading.Event(), [], {}
    original = RegisterSerializer.is_valid

    def close():
        try:
            client.post(SIGNUP, {"open": False}, format="json")
            closed.set()
        finally:
            connection.close()

    def is_valid_after_closing(serializer, **kwargs):
        # The code was checked; the manager closes the link before the application is saved.
        workers.append(threading.Thread(target=close))
        workers[0].start()
        workers[0].join(2)  # with the group locked by its code, closing waits for this registration
        seen["closed_first"] = closed.is_set()
        return original(serializer, **kwargs)

    monkeypatch.setattr(RegisterSerializer, "is_valid", is_valid_after_closing)
    r = register(code)
    workers[0].join(15)
    assert not workers[0].is_alive() and api(manager).get(SIGNUP).data == {"code": ""}
    assert (r.status_code == 201) != seen["closed_first"], (r.status_code, seen)
