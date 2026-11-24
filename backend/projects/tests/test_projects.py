import datetime

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from conftest import make_user
from projects.models import Project, ProjectLog

pytestmark = pytest.mark.django_db


def body(leader, members=(), **extra):
    return {"name": "相控阵成像", "leader_id": leader.id, "member_ids": [m.id for m in members],
            "stage": "仿真", "status": "active", "description": "", **extra}


def ids(users):
    return {u["id"] for u in users}


# --- read ---------------------------------------------------------------------------------

def test_group_members_can_read(api, project, student_b, advisor):
    ProjectLog.objects.create(project=project, date=datetime.date(2026, 11, 1), content="旧", author=student_b)
    ProjectLog.objects.create(project=project, date=datetime.date(2026, 11, 9), content="新", author=student_b)
    r = api(advisor).get("/api/projects/")
    assert r.status_code == 200 and r.data["count"] == 1
    item = r.data["results"][0]
    assert item["leader"] == {"id": project.leader_id, "name": "s_a"}
    assert item["latest_log"]["content"] == "新" and item["latest_log"]["author"]["id"] == student_b.id
    assert "leader_id" not in item
    assert api(student_b).get(f"/api/projects/{project.id}/").status_code == 200


def test_requires_login_and_changed_password(api, project, student_b):
    r = api().get("/api/projects/")
    assert r.status_code == 403 and r.data["code"] == "not_authenticated"
    student_b.must_change_password = True
    student_b.save()
    r = api(student_b).get(f"/api/projects/{project.id}/")
    assert r.status_code == 403 and r.data["code"] == "password_change_required"


def test_other_group_cannot_see_project(api, project, other_manager):
    client = api(other_manager)
    assert client.get("/api/projects/").data["count"] == 0
    assert client.get(f"/api/projects/{project.id}/").status_code == 404
    assert client.patch(f"/api/projects/{project.id}/", {"stage": "x"}, format="json").status_code == 404
    assert client.get(f"/api/projects/{project.id}/logs/").status_code == 404
    r = client.post(f"/api/projects/{project.id}/logs/", {"date": "2026-11-16", "content": "x"}, format="json")
    assert r.status_code == 404


def test_filters(api, group, project, student_a, manager):
    Project.objects.create(group=group, name="电磁超声", leader=manager, status="closed")
    client = api(student_a)

    def names(query):
        return {p["name"] for p in client.get(f"/api/projects/{query}").data["results"]}

    assert names("?status=closed") == {"电磁超声"}
    assert names("?search=螺栓") == {"导波螺栓松动"}
    assert names("?mine=1") == {"导波螺栓松动"}
    assert names("") == {"导波螺栓松动", "电磁超声"}


def test_list_has_no_n_plus_one(api, group, project, student_a, student_b, manager):
    def count_queries():
        with CaptureQueriesContext(connection) as ctx:
            assert api(student_a).get("/api/projects/").status_code == 200
        return len(ctx)

    ProjectLog.objects.create(project=project, date=datetime.date(2026, 11, 1), content="a", author=student_a)
    baseline = count_queries()
    for i in range(3):
        p = Project.objects.create(group=group, name=f"p{i}", leader=manager)
        p.members.set([student_a, student_b, manager])
        ProjectLog.objects.create(project=p, date=datetime.date(2026, 11, 2), content="b", author=manager)
    assert count_queries() == baseline


# --- create -------------------------------------------------------------------------------

@pytest.mark.parametrize("creator", ["manager", "advisor"])
def test_supervisor_creates_project_and_leader_joins(api, request, group, student_a, student_b, creator):
    r = api(request.getfixturevalue(creator)).post("/api/projects/", body(student_a, [student_b]), format="json")
    assert r.status_code == 201
    assert r.data["leader"]["id"] == student_a.id
    assert ids(r.data["members"]) == {student_a.id, student_b.id}
    assert r.data["latest_log"] is None
    assert Project.objects.get(id=r.data["id"]).group == group


def test_student_cannot_create(api, student_a):
    assert api(student_a).post("/api/projects/", body(student_a), format="json").status_code == 403


def test_create_rejects_outside_or_inactive_members(api, group, manager, student_a, other_manager):
    gone = make_user("gone", group, is_active=False)
    client = api(manager)
    r = client.post("/api/projects/", body(other_manager), format="json")
    assert r.status_code == 400 and "leader_id" in r.data["errors"]
    r = client.post("/api/projects/", body(student_a, [gone]), format="json")
    assert r.status_code == 400 and "member_ids" in r.data["errors"]
    r = client.post("/api/projects/", body(student_a, [other_manager]), format="json")
    assert r.status_code == 400 and "member_ids" in r.data["errors"]
    r = client.post("/api/projects/", {"name": "缺负责人"}, format="json")
    assert r.status_code == 400 and "leader_id" in r.data["errors"]


def test_duplicate_name_in_group_is_409(api, project, manager, student_a, other_group):
    r = api(manager).post("/api/projects/", body(student_a, name=project.name), format="json")
    assert r.status_code == 409 and r.data["code"] == "conflict"
    # The same name in another group is fine.
    other_leader = make_user("o_lead", other_group, is_manager=True)
    r = api(other_leader).post("/api/projects/", body(other_leader, name=project.name), format="json")
    assert r.status_code == 201


# --- update -------------------------------------------------------------------------------

def test_leader_updates_project_but_cannot_change_leader(api, project, student_a, student_b):
    client = api(student_a)
    r = client.patch(f"/api/projects/{project.id}/", {"stage": "现场测试", "leader_id": student_a.id}, format="json")
    assert r.status_code == 200 and r.data["stage"] == "现场测试"
    r = client.patch(f"/api/projects/{project.id}/", {"leader_id": student_b.id}, format="json")
    assert r.status_code == 403
    project.refresh_from_db()
    assert project.leader == student_a


def test_plain_member_cannot_update(api, project, student_b):
    assert api(student_b).patch(f"/api/projects/{project.id}/", {"stage": "x"}, format="json").status_code == 403


def test_supervisor_changes_leader_and_members(api, project, advisor, student_a, student_b, manager):
    url = f"/api/projects/{project.id}/"
    r = api(advisor).patch(url, {"leader_id": manager.id}, format="json")
    assert r.status_code == 200 and r.data["leader"]["id"] == manager.id
    assert ids(r.data["members"]) == {student_a.id, student_b.id, manager.id}
    # Dropping the leader from member_ids puts them back.
    r = api(advisor).patch(url, {"member_ids": [student_b.id]}, format="json")
    assert ids(r.data["members"]) == {student_b.id, manager.id}


def test_rename_to_existing_name_is_409(api, group, project, manager):
    Project.objects.create(group=group, name="电磁超声", leader=manager)
    url = f"/api/projects/{project.id}/"
    assert api(manager).patch(url, {"name": "电磁超声"}, format="json").status_code == 409
    assert api(manager).patch(url, {"name": project.name}, format="json").status_code == 200


def test_no_delete_or_put(api, project, manager):
    url = f"/api/projects/{project.id}/"
    assert api(manager).delete(url).status_code == 405
    assert api(manager).put(url, {"name": "x"}, format="json").status_code == 405


# --- logs ---------------------------------------------------------------------------------

def test_logs_newest_first_and_paginated(api, project, student_a, student_b):
    for day in (3, 10, 7):
        ProjectLog.objects.create(project=project, date=datetime.date(2026, 11, day), content=str(day), author=student_a)
    r = api(student_b).get(f"/api/projects/{project.id}/logs/?page_size=2")
    assert r.status_code == 200 and r.data["count"] == 3
    assert [log["content"] for log in r.data["results"]] == ["10", "7"]


@pytest.mark.parametrize("writer", ["student_a", "manager", "advisor"])
def test_leader_and_supervisors_add_logs(api, request, project, writer):
    user = request.getfixturevalue(writer)
    r = api(user).post(f"/api/projects/{project.id}/logs/", {"date": "2026-11-16", "content": "完成标定", "author": 999},
                       format="json")
    assert r.status_code == 201 and r.data["author"]["id"] == user.id
    assert api(user).get(f"/api/projects/{project.id}/").data["latest_log"]["content"] == "完成标定"


def test_non_member_cannot_add_log_and_bad_log_is_400(api, group, project, student_a, student_b):
    url = f"/api/projects/{project.id}/logs/"
    outsider = make_user("s_c", group)  # members may add logs since issue #48 N5; someone outside the project may not
    assert api(outsider).post(url, {"date": "2026-11-16", "content": "x"}, format="json").status_code == 403
    r = api(student_a).post(url, {"date": "16/11/2026"}, format="json")
    assert r.status_code == 400 and {"date", "content"} <= set(r.data["errors"])
