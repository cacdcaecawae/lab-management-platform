"""Issue #48 N3: ending a booking early frees the rest of its time; the paged list view; what is still to report."""
from datetime import timedelta

import pytest
from django.utils import timezone

from equipment.models import Booking, Equipment, UsageReport

pytestmark = pytest.mark.django_db


@pytest.fixture
def device(group):
    return Equipment.objects.create(group=group, code="UT-001", name="超声探伤仪")


def book(device, user, start_hours, hours=2, **extra):
    start = timezone.now().replace(second=0, microsecond=0) + timedelta(hours=start_hours)
    return Booking.objects.create(equipment=device, user=user, start_at=start, end_at=start + timedelta(hours=hours), **extra)


def test_ending_early_frees_the_rest_for_others(api, device, student_a, student_b):
    running = book(device, student_a, -1)  # under way, ends in an hour
    planned = running.end_at
    later = (timezone.now() + timedelta(minutes=5)).replace(second=0, microsecond=0)
    body = {"equipment_id": device.pk, "start_at": later.isoformat(), "end_at": (later + timedelta(minutes=30)).isoformat()}
    assert api(student_b).post("/api/bookings/", body).status_code == 409  # still taken
    ended = api(student_a).post(f"/api/bookings/{running.pk}/end-now/")
    assert ended.status_code == 200, ended.data
    running.refresh_from_db()
    assert running.planned_end_at == planned and running.end_at <= timezone.now() and running.end_at.second == 0
    assert api(student_b).post("/api/bookings/", body).status_code == 201
    assert api(student_a).post(f"/api/bookings/{running.pk}/end-now/").status_code == 409  # already over


def test_who_and_which_bookings_can_end_early(api, device, student_a, student_b, manager, other_manager):
    running = book(device, student_a, -1)
    assert api(student_b).post(f"/api/bookings/{running.pk}/end-now/").status_code == 403
    assert api(other_manager).post(f"/api/bookings/{running.pk}/end-now/").status_code == 404
    future = book(device, student_a, 5)
    assert api(student_a).post(f"/api/bookings/{future.pk}/end-now/").status_code == 409
    other = Equipment.objects.create(group=device.group, code="UT-002", name="探头")
    upkeep = book(other, manager, -1, kind=Booking.Kind.MAINTENANCE)
    assert api(manager).post(f"/api/bookings/{upkeep.pk}/end-now/").status_code == 409
    assert api(manager).post(f"/api/bookings/{running.pk}/end-now/").status_code == 200  # a manager may


def test_a_booking_just_started_keeps_one_minute(api, device, student_a):
    start = timezone.now() - timedelta(seconds=20)
    running = Booking.objects.create(equipment=device, user=student_a, start_at=start, end_at=start + timedelta(hours=1))
    planned = running.end_at
    assert api(student_a).post(f"/api/bookings/{running.pk}/end-now/").status_code == 200
    running.refresh_from_db()
    assert running.end_at == start + timedelta(minutes=1)
    # still under way for the rest of that minute, but it ends early only once: the original end is kept
    assert api(student_a).post(f"/api/bookings/{running.pk}/end-now/").status_code == 409
    running.refresh_from_db()
    assert running.planned_end_at == planned


def test_list_view_and_what_is_left_to_report(api, device, group, student_a, student_b, other_manager):
    ended = book(device, student_a, -30)
    reported = book(device, student_a, -20)
    UsageReport.objects.create(booking=reported, condition=UsageReport.Condition.NORMAL)
    running = book(device, student_a, -1)
    book(device, student_b, 3)
    stale = book(device, student_a, -24 * 20)  # too old to remind about
    cancelled = book(device, student_a, 6)
    cancelled.cancelled_at = timezone.now()
    cancelled.save()
    client = api(student_a)
    rows = client.get("/api/bookings/all/").data
    assert rows["count"] == 5 and rows["results"][-1]["id"] == stale.pk  # newest first, no cancelled
    assert [r["id"] for r in client.get("/api/bookings/all/", {"mine": "1", "pending": "1"}).data["results"]] == [ended.pk]
    reportable = client.get("/api/bookings/all/", {"mine": "1", "reportable": "1", "equipment": device.pk}).data["results"]
    assert [r["id"] for r in reportable] == [running.pk, ended.pk]
    dashboard = client.get("/api/dashboard/").data["my"]["unreported_bookings"]
    assert [b["id"] for b in dashboard] == [ended.pk]  # the workbench's 待登记使用 is the list's 待登记
    day = timezone.localtime(stale.start_at).date().isoformat()
    assert [r["id"] for r in client.get("/api/bookings/all/", {"from": day, "to": day}).data["results"]] == [stale.pk]
    assert client.get("/api/bookings/all/", {"from": "2026-13-45"}).status_code == 400
    assert client.get("/api/bookings/all/", {"equipment": "x"}).data["count"] == 0
    assert api(other_manager).get("/api/bookings/all/").data["count"] == 0
