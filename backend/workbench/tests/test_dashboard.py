import pytest

from conftest import make_user
from reports.models import WeeklyReport
from reports.queries import current_week_start
from research.models import Experiment

pytestmark = pytest.mark.django_db


def report(owner, status, week_start=None):
    return WeeklyReport.objects.create(owner=owner, week_start=week_start or current_week_start(), status=status)


def test_student_sees_own_todos_only(api, project, student_a, student_b):
    report(student_a, WeeklyReport.Status.NEEDS_REVISION)
    report(student_b, WeeklyReport.Status.NEEDS_REVISION)
    Experiment.objects.create(owner=student_a, project=project, title="mine", date="2026-11-16")
    Experiment.objects.create(owner=student_b, project=project, title="theirs", date="2026-11-16")

    data = api(student_a).get("/api/dashboard/").data
    assert [r["owner"]["id"] for r in data["my"]["reports_needing_revision"]] == [student_a.id]
    assert [e["title"] for e in data["my"]["draft_experiments"]] == ["mine"]
    assert data["my"]["current_week_report"]["owner"]["id"] == student_a.id
    assert data["supervisor"] is None


def test_supervisor_sees_missing_and_pending_in_own_group(api, project, student_a, student_b, manager, other_group):
    outsider = make_user("outsider", other_group)
    report(student_a, WeeklyReport.Status.SUBMITTED)
    report(outsider, WeeklyReport.Status.SUBMITTED)

    sup = api(manager).get("/api/dashboard/").json()["supervisor"]
    assert sup["week_start"] == current_week_start().isoformat()
    assert [u["id"] for u in sup["missing_reports"]] == [student_b.id]
    assert [r["owner"]["id"] for r in sup["pending_reviews"]] == [student_a.id]


def test_dashboard_requires_login(api, db):
    assert api().get("/api/dashboard/").status_code == 403
