import pytest
from django.db import IntegrityError, transaction

from conftest import make_user
from projects.models import Project, Task

pytestmark = pytest.mark.django_db


def project_url(project, sub="tasks"):
    return f"/api/projects/{project.pk}/{sub}/"


def detail(pk, sub="tasks"):
    return f"/api/{sub}/{pk}/"


def post(client, project, sub="tasks", **data):
    return client.post(project_url(project, sub), {"title": "合成记录", **data}, format="json")


def patch(client, obj_id, sub="tasks", **data):
    return client.patch(detail(obj_id, sub), data, format="json")


def test_permissions(api, project, student_a, student_b, manager, advisor, other_manager):
    project.members.add(student_a)
    project.members.remove(student_b)
    member = api(student_a)
    nonmember = api(student_b)
    manage = api(manager)
    outside = api(other_manager)
    assert post(nonmember, project).status_code == 403
    task = post(member, project, assignee_id=student_a.pk)
    assert task.status_code == 201, task.data
    task_id = task.data["id"]
    assert nonmember.get(project_url(project)).data["count"] == 1
    assert patch(nonmember, task_id, status="doing").status_code == 403
    assert manage.get(project_url(project)).data["count"] == 1
    assert patch(api(advisor), task_id, status="doing").status_code == 200
    assert outside.get(project_url(project)).status_code == 404
    assert post(outside, project, "milestones").status_code == 404
    assert patch(outside, task_id, status="done").status_code == 404
    assert outside.delete(detail(task_id)).status_code == 404
    assert nonmember.delete(detail(task_id)).status_code == 403
    assert post(nonmember, project, "milestones").status_code == 403
    assert project.leader_id != student_a.pk or post(member, project, "milestones").status_code == 201
    project.members.remove(student_a)
    assert member.delete(detail(task_id)).status_code == 204


def test_milestone_integrity_progress_and_history(api, project, group, student_a, manager, advisor, other_manager):
    lead = api(project.leader)
    project.members.add(student_a)
    member = api(student_a)
    manage = api(manager)
    other_project = Project.objects.create(group=group, name="同组的其他项目", leader=manager)
    other_m = post(manage, other_project, "milestones").data["id"]
    assert post(member, project, milestone_id=other_m).status_code == 400
    with pytest.raises(IntegrityError), transaction.atomic():
        Task.objects.create(project=project, title="不合法", created_by=student_a, milestone_id=other_m)
    milestone = post(lead, project, "milestones", due_date="2027-02-01")
    assert milestone.status_code == 201
    m = milestone.data["id"]
    assert patch(api(other_manager), m, "milestones", done=True).status_code == 404
    entry = post(member, project, milestone_id=m)
    assert entry.status_code == 201, entry.data
    task_id = entry.data["id"]
    assert patch(api(advisor), task_id, milestone_id=other_m).status_code == 400
    assert patch(member, task_id, status="done").data["history"][0]["changes"] == {
        "status": {"before": "todo", "after": "done"},
    }
    assert patch(member, task_id, status="done").data["history"][0]["actor"] == student_a.name
    milestone = patch(lead, m, "milestones", done=True)
    assert milestone.data["done_at"]
    assert milestone.data["task_done"] == milestone.data["task_total"] == 1
    assert patch(lead, m, "milestones", done=True).data["done_at"] == milestone.data["done_at"]
    assert lead.delete(detail(m, "milestones")).status_code == 204
    rows = member.get(project_url(project) + "?status=done").data["results"]
    assert rows[0]["milestone"] is None
    assert rows[0]["history"][0]["changes"] == {"milestone": {"before": "合成记录", "after": None}}
    assert len(rows[0]["history"]) == 3


def test_assignment_departure_and_dashboard(api, project, group, student_a, student_b, advisor, other_manager):
    supervisor = api(advisor)
    project.members.add(student_b)
    p = project
    new = post(supervisor, p, assignee_id=student_b.pk).data
    task_id = new["id"]
    assert new["assignee"]["current"]
    assert post(supervisor, p, assignee_id=other_manager.pk).status_code == 400
    assert post(supervisor, p, assignee_id=advisor.pk).status_code == 400
    Task.objects.create(project=p, title="有日期", assignee=student_b, created_by=student_a, due_date="2027-01-01")
    Task.objects.create(project=p, title="已完成", assignee=student_b, created_by=student_a, status=Task.Status.DONE)
    assert [r["title"] for r in api(student_b).get("/api/dashboard/").data["my"]["tasks"]] == ["有日期", "合成记录"]
    p.members.remove(student_b)
    assert api(student_b).get("/api/dashboard/").data["my"]["tasks"] == []
    assert patch(supervisor, task_id, assignee_id=student_b.pk).status_code == 400
    student_b.group = other_manager.group
    student_b.name = "新组的名字"
    student_b.save()
    edited = patch(supervisor, task_id, status="doing")
    assert edited.data["assignee"] == {"id": student_b.pk, "name": new["assignee"]["name"], "current": False}
    assert edited.data["history"][0]["changes"] == {"status": {"before": "todo", "after": "doing"}}
    assert api(student_b).get("/api/dashboard/").data["my"]["tasks"] == []
    assert patch(supervisor, task_id, assignee_id=None).data["assignee"] is None


def test_dashboard_task_limit_and_validation(api, project, student_a):
    project.members.add(student_a)
    Task.objects.bulk_create([
        Task(project=project, title=f"任务 {i}", assignee=student_a, created_by=student_a)
        for i in range(21)
    ])
    client = api(student_a)
    assert len(client.get("/api/dashboard/").data["my"]["tasks"]) == 20
    assert client.get(project_url(project) + "?status=unknown").status_code == 400
    assert client.get(project_url(project) + "?assignee=bad").status_code == 400


def test_a_member_without_a_name_is_shown_by_username(api, project, group):
    nameless = make_user("s_c", group, name="")
    project.members.add(nameless)
    task_id = post(api(nameless), project, assignee_id=nameless.id).data["id"]
    edited = patch(api(nameless), task_id, status="doing").data
    assert edited["history"][0]["actor"] == "s_c" and edited["assignee"]["name"] == "s_c"
