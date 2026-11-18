"""Behaviour shared by /api/experiments/ and /api/runs/: state machine, permissions, isolation,
history. Every test runs once per resource."""

import datetime

import pytest

from projects.models import Project
from reports.models import WeeklyReport

from .factories import make_experiment, make_run

pytestmark = pytest.mark.django_db


@pytest.fixture(params=["experiments", "runs"])
def resource(request):
    return request.param


@pytest.fixture
def record(resource, student_a, project):
    """A draft owned by student_a."""
    return (make_experiment if resource == "experiments" else make_run)(student_a, project)


def url(resource, obj=None, action=None):
    path = f"/api/{resource}/"
    if obj is not None:
        path += f"{obj.pk}/"
    if action:
        path += f"{action}/"
    return path


def submitted(resource, record, client):
    response = client.post(url(resource, record, "submit"))
    assert response.status_code == 200, response.json()
    return response.json()


# --- state machine -------------------------------------------------------------------------


def test_owner_patches_draft_and_cannot_set_status(api, resource, record, student_a):
    response = api(student_a).patch(url(resource, record), {"title": "新标题", "status": "submitted"}, format="json")
    assert response.status_code == 200
    assert response.json()["title"] == "新标题"
    assert response.json()["status"] == "draft"


def test_submit_draft_then_submit_again_is_409(api, resource, record, student_a):
    client = api(student_a)
    body = submitted(resource, record, client)
    assert body["status"] == "submitted" and body["submitted_at"]

    response = client.post(url(resource, record, "submit"))
    assert response.status_code == 409
    assert response.json()["code"] == "invalid_state"


def test_submitted_record_cannot_be_patched_or_deleted(api, resource, record, student_a):
    client = api(student_a)
    submitted(resource, record, client)
    for response in (client.patch(url(resource, record), {"title": "x"}, format="json"), client.delete(url(resource, record))):
        assert response.status_code == 409
        assert response.json()["code"] == "invalid_state"


def test_supervisor_returns_with_reason_and_owner_can_edit_again(api, resource, record, student_a, advisor):
    submitted(resource, record, api(student_a))

    response = api(advisor).post(url(resource, record, "return"), {"reason": "缺少试件编号"}, format="json")
    assert response.status_code == 200
    assert response.json()["status"] == "draft"
    assert response.json()["submitted_at"] is None

    newest = api(student_a).get(url(resource, record, "history")).json()[0]
    assert newest["reason"] == "缺少试件编号"
    assert newest["user"]["id"] == advisor.id
    assert {"field": "status", "old": "submitted", "new": "draft"} in newest["changes"]

    assert api(student_a).patch(url(resource, record), {"title": "补充后"}, format="json").status_code == 200


def test_return_requires_a_reason(api, resource, record, student_a, manager):
    submitted(resource, record, api(student_a))
    for body in ({}, {"reason": "   "}):
        response = api(manager).post(url(resource, record, "return"), body, format="json")
        assert response.status_code == 400
        assert "reason" in response.json()["errors"]


def test_only_submitted_records_can_be_returned(api, resource, record, manager):
    response = api(manager).post(url(resource, record, "return"), {"reason": "x"}, format="json")
    assert response.status_code == 409
    assert response.json()["code"] == "invalid_state"


def test_history_newest_first(api, resource, record, student_a):
    submitted(resource, record, api(student_a))
    history = api(student_a).get(url(resource, record, "history")).json()
    assert [entry["type"] for entry in history] == ["changed", "created"]
    assert {"field": "status", "old": "draft", "new": "submitted"} in history[0]["changes"]


def test_delete_draft(api, resource, record, student_a):
    assert api(student_a).delete(url(resource, record)).status_code == 204
    assert api(student_a).get(url(resource, record)).status_code == 404


def test_cannot_delete_record_used_by_weekly_report(api, resource, record, student_a):
    report = WeeklyReport.objects.create(owner=student_a, week_start=datetime.date(2026, 11, 16))
    (report.experiments if resource == "experiments" else report.runs).add(record)

    response = api(student_a).delete(url(resource, record))
    assert response.status_code == 409
    assert response.json()["code"] == "invalid_state"
    assert type(record).objects.filter(pk=record.pk).exists()


def test_put_is_not_supported(api, resource, record, student_a):
    assert api(student_a).put(url(resource, record), {"title": "x"}, format="json").status_code == 405


# --- permissions ---------------------------------------------------------------------------


def test_students_cannot_return(api, resource, record, student_a, student_b):
    submitted(resource, record, api(student_a))
    for student in (student_a, student_b):
        response = api(student).post(url(resource, record, "return"), {"reason": "x"}, format="json")
        assert response.status_code == 403


def test_supervisor_cannot_write_someone_elses_record(api, resource, record, manager):
    client = api(manager)
    assert client.patch(url(resource, record), {"title": "x"}, format="json").status_code == 403
    assert client.post(url(resource, record, "submit")).status_code == 403
    assert client.delete(url(resource, record)).status_code == 403


# --- isolation -----------------------------------------------------------------------------


def test_other_student_gets_404(api, resource, record, student_b):
    client = api(student_b)
    assert client.get(url(resource, record)).status_code == 404
    assert client.patch(url(resource, record), {"title": "x"}, format="json").status_code == 404
    assert client.delete(url(resource, record)).status_code == 404
    assert client.post(url(resource, record, "submit")).status_code == 404
    assert client.get(url(resource, record, "history")).status_code == 404
    assert client.get(url(resource)).json()["count"] == 0


def test_other_group_supervisor_gets_404(api, resource, record, student_a, other_manager):
    submitted(resource, record, api(student_a))
    client = api(other_manager)
    assert client.get(url(resource, record)).status_code == 404
    assert client.get(url(resource, record, "history")).status_code == 404
    assert client.post(url(resource, record, "return"), {"reason": "x"}, format="json").status_code == 404
    assert client.get(url(resource)).json()["count"] == 0


def test_group_supervisors_can_read(api, resource, record, manager, advisor):
    for supervisor in (manager, advisor):
        client = api(supervisor)
        assert client.get(url(resource, record)).status_code == 200
        assert client.get(url(resource, record, "history")).status_code == 200
        assert [r["id"] for r in client.get(url(resource)).json()["results"]] == [record.pk]


# --- list filters --------------------------------------------------------------------------


def test_list_filters(api, resource, record, student_a, student_b, group, manager):
    make = make_experiment if resource == "experiments" else make_run
    other_project = Project.objects.create(group=group, name="另一个项目", leader=student_b)
    theirs = make(student_b, other_project, title="别人的记录")
    submitted(resource, theirs, api(student_b))

    client = api(manager)

    def ids(**params):
        return {r["id"] for r in client.get(url(resource), params).json()["results"]}

    assert ids() == {record.pk, theirs.pk}
    assert ids(project=other_project.pk) == {theirs.pk}
    assert ids(owner=student_a.pk) == {record.pk}
    assert ids(status="submitted") == {theirs.pk}
    assert ids(search="别人") == {theirs.pk}
    assert ids(status="bogus") == ids(status="\x00") == set()
    assert client.get(url(resource), {"project": "abc"}).status_code == 400
    assert client.get(url(resource), {"search": "\x00"}).status_code == 400
