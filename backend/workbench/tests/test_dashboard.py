from datetime import timedelta

import pytest
from django.utils import timezone

from conftest import make_user
from equipment.models import Booking, Equipment
from reports.models import WeeklyReport
from reports.queries import current_week_start
from research.models import Experiment
from specimens.models import Defect, Specimen, SpecimenLoan

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


def test_advisor_sees_missing_and_pending_in_own_group(api, project, student_a, student_b, manager, advisor, other_group):
    outsider = make_user("outsider", other_group)
    report(student_a, WeeklyReport.Status.SUBMITTED)
    report(outsider, WeeklyReport.Status.SUBMITTED)

    sup = api(advisor).get("/api/dashboard/").json()["supervisor"]
    assert sup["week_start"] == current_week_start().isoformat()
    # the manager is a student too (the 管理员 tag): one more weekly report to hand in
    assert sorted(u["id"] for u in sup["missing_reports"]) == sorted([student_b.id, manager.id])
    assert [r["owner"]["id"] for r in sup["pending_reviews"]] == [student_a.id]
    # a student with the 管理员 tag: purchases to review, but no weekly reports of others
    sup = api(manager).get("/api/dashboard/").json()["supervisor"]
    assert sup["missing_reports"] == sup["pending_reviews"] == []


def test_dashboard_requires_login(api, db):
    assert api().get("/api/dashboard/").status_code == 403


def test_borrowing_reminders_match_filters_preview_count_and_roles(
    api, group, other_group, student_a, student_b, manager, other_manager, advisor,
):
    today = timezone.localdate()

    def loan(code, borrower, due_date, returned=False):
        return SpecimenLoan.objects.create(
            specimen=Specimen.objects.create(group=borrower.group, code=code, name=code),
            borrower=borrower,
            due_date=due_date,
            returned_at=timezone.now() if returned else None,
        )

    late = loan("late", student_a, today - timedelta(days=1))
    due_today = loan("today", student_a, today)
    undated = loan("undated", student_a, None)
    loan("done", student_a, today - timedelta(days=2), returned=True)
    other_late = loan("other-student", student_b, today - timedelta(days=2))
    loan("other-group", other_manager, today - timedelta(days=3))
    Defect.objects.create(specimen=late.specimen, kind=Defect.Kind.CRACK, size_mm=2)

    own = api(student_a)
    data = own.get("/api/dashboard/").json()
    assert data["manager"] is None
    assert data["my"]["borrowed_specimens_count"] == 3
    cards = data["my"]["borrowed_specimens"]
    assert [(x["loan_id"], x["overdue"]) for x in cards] == [
        (late.pk, True), (due_today.pk, False), (undated.pk, False),
    ]
    assert all("defects" not in x["specimen"] and "borrower" not in x for x in cards)
    assert own.get("/api/specimens/?mine=1").json()["count"] == 3
    assert [row["id"] for row in own.get("/api/specimens/?mine=1&overdue=1").json()["results"]] == [late.specimen_id]

    mgr = api(manager)
    assert {x["id"] for x in mgr.get("/api/specimens/?overdue=1").json()["results"]} == {
        late.specimen_id, other_late.specimen_id,
    }
    for i in range(21):
        loan(f"more-{i:02d}", student_b, today - timedelta(days=3))
    reminders = mgr.get("/api/dashboard/").json()["manager"]
    assert reminders["overdue_loans_count"] == mgr.get("/api/specimens/?overdue=1").json()["count"] == 23
    assert len(reminders["overdue_loans"]) == 20
    assert all(x["borrower"]["id"] == student_b.pk for x in reminders["overdue_loans"])
    assert api(advisor).get("/api/dashboard/").json()["manager"] is None
    assert api(other_manager).get("/api/dashboard/").json()["manager"]["overdue_loans_count"] == 1


def test_calibration_reminders_match_filter_including_date_boundaries(api, group, other_group, manager):
    today = timezone.localdate()

    def equipment(code, due, status=Equipment.Status.AVAILABLE, lab=group):
        return Equipment.objects.create(group=lab, code=code, name=code, calibration_due=due, status=status)

    late = equipment("late", today - timedelta(days=1))
    now = equipment("today", today)
    edge = equipment("edge", today + timedelta(days=30))
    equipment("future", today + timedelta(days=31))
    equipment("none", None)
    equipment("retired", today, Equipment.Status.RETIRED)
    equipment("outside", today, lab=other_group)
    mgr = api(manager)
    reminders = mgr.get("/api/dashboard/").json()["manager"]
    listed = mgr.get("/api/equipment/?calibration_within=30").json()
    expected = [late.pk, now.pk, edge.pk]
    assert [x["id"] for x in reminders["calibration_due"]] == [x["id"] for x in listed["results"]] == expected
    assert reminders["calibration_due_count"] == listed["count"] == 3
    assert mgr.get("/api/equipment/?calibration_within=0").json()["count"] == 2
    assert mgr.get("/api/equipment/?calibration_within=-1").status_code == 400
    assert mgr.get("/api/equipment/?calibration_within=no").status_code == 400


def test_bookings_of_a_former_group_stay_out_of_sight(api, group, other_group, student_a):
    device = Equipment.objects.create(group=group, code="UT-001", name="超声探伤仪")
    start = timezone.now() + timedelta(hours=2)
    Booking.objects.create(equipment=device, user=student_a, start_at=start, end_at=start + timedelta(hours=1))
    assert len(api(student_a).get("/api/dashboard/").data["my"]["upcoming_bookings"]) == 1
    student_a.group = other_group  # moved to another group
    student_a.save()
    assert api(student_a).get("/api/dashboard/").data["my"]["upcoming_bookings"] == []
