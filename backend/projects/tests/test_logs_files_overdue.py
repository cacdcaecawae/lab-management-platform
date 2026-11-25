"""Issue #58 P4-1: progress logs can be changed and deleted, project files, the list's leader and overdue filters."""
import datetime
from pathlib import Path

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from conftest import make_user
from projects.models import Project, ProjectFile, ProjectLog, Task

pytestmark = pytest.mark.django_db


def test_who_changes_and_deletes_a_progress_log(api, group, project, student_a, student_b, manager, advisor, other_manager):
    outsider = make_user("s_c", group)  # in the group, not in the project
    project.members.add(outsider)
    log = ProjectLog.objects.create(project=project, date=datetime.date(2026, 11, 20), content="标定", author=student_b)
    url = f"/api/project-logs/{log.pk}/"

    r = api(student_b).patch(url, {"content": "完成标定"}, format="json")  # the author
    assert r.status_code == 200 and r.data["content"] == "完成标定" and r.data["author"]["id"] == student_b.pk
    for user in (student_a, advisor, manager):  # the leader and supervisors
        assert api(user).patch(url, {"date": "2026-11-21"}, format="json").status_code == 200
    refused = api(outsider).patch(url, {"content": "改别人的"}, format="json")  # a member, not the author
    assert refused.status_code == 403 and refused.data["message"] == "仅记录人、项目负责人、管理员或导师可以修改或删除进展"
    assert api(outsider).delete(url).status_code == 403
    assert api(other_manager).patch(url, {"content": "x"}, format="json").status_code == 404
    assert api(other_manager).delete(url).status_code == 404
    assert api(student_b).patch(url, {"date": ""}, format="json").status_code == 400
    assert api(student_b).put(url, {"date": "2026-11-21", "content": "x"}, format="json").status_code == 405

    assert api(student_a).delete(url).status_code == 204
    assert not ProjectLog.objects.exists()


def test_project_files(api, django_capture_on_commit_callbacks, group, project, student_a, student_b, manager, other_manager):
    outsider = make_user("s_c", group)
    url = f"/api/projects/{project.pk}/files/"
    r = api(student_b).post(url, {"file": SimpleUploadedFile("开题报告.pdf", b"%PDF-1.4")})  # a member
    assert r.status_code == 201 and r.data["name"] == "开题报告.pdf" and r.data["uploaded_by"]["id"] == student_b.pk
    refused = api(outsider).post(url, {"file": SimpleUploadedFile("x.pdf", b"x")})
    assert refused.status_code == 403 and refused.data["message"] == "仅本项目成员、管理员或导师可以上传文件"
    assert api(manager).post(url, {"file": SimpleUploadedFile("中期.docx", b"PK")}).status_code == 201
    assert api(student_a).post(url, {}).status_code == 400

    listed = api(outsider).get(url)  # the whole group reads them
    assert [f["name"] for f in listed.data] == ["开题报告.pdf", "中期.docx"]
    pdf = api(outsider).get(r.data["url"])
    assert pdf.status_code == 200 and b"".join(pdf.streaming_content) == b"%PDF-1.4"
    assert api(other_manager).get(url).status_code == 404
    assert api(other_manager).get(r.data["url"]).status_code == 404
    assert api(other_manager).delete(f"/api/project-files/{r.data['id']}/").status_code == 404

    docx = ProjectFile.objects.get(name="中期.docx")
    assert api(student_b).delete(f"/api/project-files/{docx.pk}/").status_code == 403  # not the uploader or leader
    stored = Path(settings.MEDIA_ROOT) / docx.file.name
    with django_capture_on_commit_callbacks(execute=True):
        assert api(student_a).delete(f"/api/project-files/{docx.pk}/").status_code == 204  # the leader
    assert not stored.exists()
    assert api(student_b).delete(f"/api/project-files/{r.data['id']}/").status_code == 204  # the uploader


def test_list_counts_overdue_tasks_and_filters_by_leader(api, group, project, student_a, student_b, manager):
    today = timezone.localdate()
    late, soon = today - datetime.timedelta(days=1), today + datetime.timedelta(days=3)
    other = Project.objects.create(group=group, name="电磁超声", leader=student_b)
    quiet = Project.objects.create(group=group, name="无任务", leader=student_b)
    quiet.members.add(student_a)
    for title, due, state in (("逾期一", late, "todo"), ("逾期二", late, "doing"), ("已完成", late, "done"), ("未到期", soon, "todo")):
        Task.objects.create(project=project, title=title, due_date=due, status=state, created_by=student_a)
    Task.objects.create(project=other, title="没有截止日期", created_by=student_b)

    def listed(user, query=""):
        return {p["name"]: p["overdue_tasks"] for p in api(user).get(f"/api/projects/{query}").data["results"]}

    assert listed(manager) == {"导波螺栓松动": 2, "电磁超声": 0, "无任务": 0}
    assert listed(student_a, "?mine=1") == {"导波螺栓松动": 2, "无任务": 0}  # joining the members does not double it
    assert listed(manager, "?overdue=1") == {"导波螺栓松动": 2}
    assert listed(manager, f"?leader={student_b.pk}") == {"电磁超声": 0, "无任务": 0}
    assert listed(manager, f"?leader={student_b.pk}&overdue=1") == {}
    assert listed(manager, "?leader=abc") == {}
    assert api(student_b).get(f"/api/projects/{project.pk}/").data["overdue_tasks"] == 2
