"""Base role and the two tags, member details, the roster (issue #48 R1, S1)."""

import importlib
import io

import pytest
from django.apps import apps
from openpyxl import load_workbook

from accounts.models import User
from conftest import make_user

pytestmark = pytest.mark.django_db


def test_old_roles_become_a_base_role_and_tags(group):
    migration = importlib.import_module("accounts.migrations.0006_roles_and_identity")
    old_manager, old_advisor = make_user("old_mgr", group), make_user("old_adv", group, User.Role.ADVISOR)
    User.objects.filter(pk=old_manager.pk).update(role="manager")  # as stored before the change
    migration.split_roles(apps, None)
    old_manager.refresh_from_db()
    old_advisor.refresh_from_db()
    assert (old_manager.role, old_manager.is_manager, old_manager.is_approver) == ("student", True, False)
    assert (old_advisor.role, old_advisor.is_manager, old_advisor.is_approver) == ("advisor", False, True)
    migration.join_roles(apps, None)
    assert User.objects.get(pk=old_manager.pk).role == "manager"


def test_the_approver_gives_and_takes_back_the_manager_tag(api, group, student_a, manager, advisor, ops):
    url = f"/api/members/{student_a.id}/manager/"
    for outsider in (student_a, manager):  # a manager cannot make more managers
        assert api(outsider).post(url, {"is_manager": True}, format="json").status_code == 403
    r = api(advisor).post(url, {"is_manager": True}, format="json")
    assert r.status_code == 200 and r.data["is_manager"] is True
    student_a.refresh_from_db()
    assert student_a.is_manager and not student_a.is_approver and student_a.role == "student"
    assert api(advisor).post(url, {"is_manager": False}, format="json").data["is_manager"] is False
    ops.group = group  # a superuser in the group: never through the members page
    ops.save()
    assert api(advisor).post(f"/api/members/{ops.id}/manager/", {"is_manager": True}, format="json").status_code == 404


def test_a_student_manager_runs_affairs_without_other_students_records(api, manager, student_b):
    client = api(manager)
    assert client.get("/api/members/?status=active").status_code == 200
    assert client.post("/api/equipment/", {"code": "UT-1", "name": "探伤仪", "status": "available"}, format="json").status_code == 201
    assert client.get("/api/reports/missing/").status_code == 403


def test_member_details_status_filters_and_roster(api, group, student_a, student_b, manager, advisor):
    client = api(manager)
    r = client.patch(f"/api/members/{student_b.id}/", {
        "identity": "master", "enrollment_year": 2022, "member_status": "graduated", "tags": [" 安全员 ", "安全员", ""],
    }, format="json")
    assert r.status_code == 200, r.data
    assert (r.data["identity"], r.data["enrollment_year"], r.data["member_status"], r.data["tags"]) == ("master", 2022, "graduated", ["安全员"])
    student_b.refresh_from_db()
    assert not student_b.is_active and student_b.graduated  # graduated: does not sign in
    client.patch(f"/api/members/{student_a.id}/", {"identity": "phd", "enrollment_year": 2024, "tags": ["博导"]}, format="json")

    def names(query):
        return {row["name"] for row in client.get(f"/api/members/?{query}").data["results"]}

    assert names("status=graduated") == {"s_b"}
    assert names("status=active") == {"s_a", "mgr", "adv"}
    assert names("status=disabled") == set()
    assert names("identity=phd") == {"s_a"} and names("year=2024") == {"s_a"} and names("tag=博导") == {"s_a"}
    assert names("flag=approver") == {"adv"}
    for odd in ("identity=nope", "year=²", "status=nope", "flag=nope", "tag=%00"):
        assert names(odd) == set()
    assert client.patch(f"/api/members/{student_a.id}/", {"enrollment_year": 1800}, format="json").status_code == 400
    assert client.patch(f"/api/members/{manager.id}/", {"member_status": "disabled"}, format="json").status_code == 400  # self

    # back in the group: 在籍 again, no longer marked graduated
    assert client.patch(f"/api/members/{student_b.id}/", {"member_status": "active"}, format="json").data["member_status"] == "active"
    student_b.refresh_from_db()
    assert student_b.is_active and not student_b.graduated

    roster = client.get("/api/members/export/", {"identity": "phd"})
    assert roster.status_code == 200 and roster["Content-Disposition"].startswith("attachment")
    rows = list(load_workbook(io.BytesIO(roster.content))["花名册"].iter_rows(values_only=True))
    assert rows[0][:3] == ("姓名", "学号 / 工号", "基础角色") and [r[0] for r in rows[1:]] == ["s_a"]
    assert rows[1][5:9] == ("博士生", "2024级", "在籍", "博导")
    assert api(student_a).get("/api/members/export/").status_code == 403  # login names and contact details
