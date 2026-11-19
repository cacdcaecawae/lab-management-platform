import threading
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from conftest import enable_mail, make_user
from equipment.models import Booking, Equipment, UsageReport
from equipment.views import EquipmentViewSet

pytestmark = pytest.mark.django_db


@pytest.fixture
def scope(group):
    return Equipment.objects.create(group=group, code="UT-001", name="超声探伤仪", model="CTS-9009")


def at(hours):
    """A time `hours` from now, rounded to the minute."""
    return (timezone.now() + timedelta(hours=hours)).replace(second=0, microsecond=0)


def book(equipment, user, start, hours=1, **extra):
    """Insert directly (no API checks), e.g. bookings in the past."""
    return Booking.objects.create(equipment=equipment, user=user, start_at=at(start), end_at=at(start + hours), **extra)


def booking_body(equipment, start=2, hours=1, **extra):
    return {"equipment_id": equipment.id, "start_at": at(start).isoformat(), "end_at": at(start + hours).isoformat(), **extra}


# --- equipment ledger ---------------------------------------------------------------------

def test_only_managers_create_and_edit(api, group, student_a, advisor, manager, scope):
    body = {"code": "PA-001", "name": "相控阵", "status": "available"}
    assert api(student_a).post("/api/equipment/", body).status_code == 403
    assert api(advisor).post("/api/equipment/", body).status_code == 403
    r = api(manager).post("/api/equipment/", {**body, "custodian_id": student_a.id})
    assert r.status_code == 201 and r.data["custodian"]["id"] == student_a.id and r.data["in_use"] is False
    assert Equipment.objects.get(pk=r.data["id"]).group == group
    assert api(student_a).patch(f"/api/equipment/{scope.id}/", {"status": "repair"}).status_code == 403
    body = {"status": "repair", "status_seen": "available"}
    assert api(manager).patch(f"/api/equipment/{scope.id}/", body).data["status"] == "repair"
    assert api(student_a).get(f"/api/equipment/{scope.id}/").status_code == 200


def test_code_is_unique_per_group(api, manager, other_manager, scope):
    r = api(manager).post("/api/equipment/", {"code": "UT-001", "name": "另一台"})
    assert r.status_code == 409
    assert api(other_manager).post("/api/equipment/", {"code": "UT-001", "name": "外组的"}).status_code == 201


def test_custodian_must_be_in_group(api, manager, other_manager):
    r = api(manager).post("/api/equipment/", {"code": "X-1", "name": "x", "custodian_id": other_manager.id})
    assert r.status_code == 400 and "custodian_id" in r.data["errors"]


def test_other_group_gets_404(api, other_manager, student_a, scope):
    booking = book(scope, student_a, 2)
    client = api(other_manager)
    assert client.get("/api/equipment/").data["count"] == 0
    assert client.get(f"/api/equipment/{scope.id}/").status_code == 404
    assert client.patch(f"/api/equipment/{scope.id}/", {"name": "x"}).status_code == 404
    assert client.get(f"/api/bookings/{booking.id}/").status_code == 404
    assert client.post(f"/api/bookings/{booking.id}/cancel/").status_code == 404
    assert client.post("/api/bookings/", booking_body(scope, 5)).status_code == 400  # unknown equipment id
    r = client.get("/api/bookings/", {"from": at(0).isoformat(), "to": at(24).isoformat()})
    assert r.data == []


def test_patch_keeps_status_set_by_abnormal_report(api, student_a, student_b, manager, scope):
    """F1: an edit that does not send status must not undo "needs_check"."""
    report(api(student_a), book(scope, student_a, -2), condition="abnormal", description="无回波")
    r = api(manager).patch(f"/api/equipment/{scope.id}/", {"location": "B210"})
    assert r.status_code == 200 and r.data["status"] == "needs_check" and r.data["location"] == "B210"
    assert api(student_b).post("/api/bookings/", booking_body(scope)).status_code == 409


def test_status_change_from_a_stale_form_is_409(api, student_a, manager, scope):
    """R1: the manager picked "repair" in a form that still showed "available"; an abnormal report came in since."""
    report(api(student_a), book(scope, student_a, -2), condition="abnormal", description="无回波")
    r = api(manager).patch(f"/api/equipment/{scope.id}/", {"status": "repair", "status_seen": "available"})
    assert r.status_code == 409 and r.data["code"] == "stale_status" and "待检查" in r.data["message"]
    scope.refresh_from_db()
    assert scope.status == "needs_check"
    # Seen "needs_check": the manager handles the report.
    r = api(manager).patch(f"/api/equipment/{scope.id}/", {"status": "repair", "status_seen": "needs_check"})
    assert r.status_code == 200 and r.data["status"] == "repair"


def test_status_change_needs_status_seen(api, manager, scope):
    r = api(manager).patch(f"/api/equipment/{scope.id}/", {"status": "repair"})
    assert r.status_code == 400 and "status_seen" in r.data["errors"]


def test_status_seen_mismatch_is_fine_when_already_at_the_new_status(api, manager, scope):
    # Someone else already set "repair": writing "repair" again overwrites nothing.
    scope.status = "repair"
    scope.save()
    r = api(manager).patch(f"/api/equipment/{scope.id}/", {"status": "repair", "status_seen": "available"})
    assert r.status_code == 200 and r.data["status"] == "repair"


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "body, code, final",
    [
        ({"location": "B210"}, 200, "needs_check"),  # F1
        ({"location": "B210", "status": "repair", "status_seen": "available"}, 409, "needs_check"),  # R1
    ],
)
def test_patch_racing_abnormal_report_keeps_needs_check(api, monkeypatch, student_a, student_b, manager, scope, body, code, final):
    """F1 / R1, server side: the abnormal report commits after the PATCH read the equipment and before it saves."""
    started = book(scope, student_a, -2)
    read_done, go = threading.Event(), threading.Event()
    get_object = EquipmentViewSet.get_object

    def paused_get_object(view):
        obj = get_object(view)
        if view.action == "partial_update":
            read_done.set()
            go.wait(10)
        return obj

    monkeypatch.setattr(EquipmentViewSet, "get_object", paused_get_object)
    result = {}

    def edit():
        try:
            result["response"] = api(manager).patch(f"/api/equipment/{scope.id}/", body)
        finally:
            connection.close()  # the thread's own connection; left open it blocks dropping the test database

    thread = threading.Thread(target=edit)
    thread.start()
    assert read_done.wait(10)
    assert report(api(student_a), started, condition="abnormal", description="无回波").status_code == 201
    go.set()
    thread.join(10)
    assert not thread.is_alive()
    assert result["response"].status_code == code
    scope.refresh_from_db()
    assert scope.status == final and scope.history.first().status == final
    assert api(student_b).post("/api/bookings/", booking_body(scope, 5)).status_code == 409


def test_history_records_status_changes(api, manager, scope):
    api(manager).patch(f"/api/equipment/{scope.id}/", {"status": "repair", "status_seen": "available"})
    history = api(manager).get(f"/api/equipment/{scope.id}/history/").data
    assert {"field": "status", "old": "available", "new": "repair"} in history[0]["changes"]


# --- bookings -----------------------------------------------------------------------------

def test_overlapping_booking_is_409_and_adjacent_is_fine(api, student_a, student_b, scope):
    assert api(student_a).post("/api/bookings/", booking_body(scope, 2, 2)).status_code == 201
    r = api(student_b).post("/api/bookings/", booking_body(scope, 3, 2))
    assert r.status_code == 409 and r.data["code"] == "conflict"
    assert api(student_b).post("/api/bookings/", booking_body(scope, 4, 1)).status_code == 201  # starts when the first ends
    assert api(student_b).post("/api/bookings/", booking_body(scope, 1, 1)).status_code == 201  # ends when the first starts


def test_database_rejects_overlap_directly(student_a, student_b, scope):
    """The guarantee for concurrent requests: the exclusion constraint, not the API."""
    book(scope, student_a, 2, 2)
    with pytest.raises(IntegrityError), transaction.atomic():
        book(scope, student_b, 3, 2)
    cancelled = book(scope, student_b, 10, 1, cancelled_at=timezone.now())
    book(scope, student_a, 10, 1)  # a cancelled booking does not hold its slot
    assert cancelled.cancelled_at


def test_cancelled_booking_frees_the_slot(api, student_a, student_b, scope):
    booking_id = api(student_a).post("/api/bookings/", booking_body(scope, 2)).data["id"]
    assert api(student_a).post(f"/api/bookings/{booking_id}/cancel/").status_code == 200
    assert api(student_b).post("/api/bookings/", booking_body(scope, 2)).status_code == 201


def test_time_rules(api, student_a, scope):
    r = api(student_a).post("/api/bookings/", booking_body(scope, -1))
    assert r.status_code == 400 and "start_at" in r.data["errors"]
    r = api(student_a).post("/api/bookings/", booking_body(scope, 2, 0))
    assert r.status_code == 400 and "end_at" in r.data["errors"]


@pytest.mark.parametrize("state", ["needs_check", "repair", "retired"])
def test_only_available_equipment_can_be_booked_for_use(api, student_a, manager, scope, state):
    scope.status = state
    scope.save()
    r = api(student_a).post("/api/bookings/", booking_body(scope))
    assert r.status_code == 409 and r.data["code"] == "invalid_state"
    # Maintenance bookings reserve time for calibration or repair, whatever the status.
    assert api(manager).post("/api/bookings/", booking_body(scope, kind="maintenance")).status_code == 201
    scope.status = "available"
    scope.save()
    assert api(student_a).post("/api/bookings/", booking_body(scope, 5)).status_code == 201


def test_only_managers_book_maintenance(api, student_a, advisor, scope):
    assert api(student_a).post("/api/bookings/", booking_body(scope, kind="maintenance")).status_code == 403
    assert api(advisor).post("/api/bookings/", booking_body(scope, kind="maintenance")).status_code == 403


def test_use_bookings_last_at_most_seven_days(api, student_a, manager, scope):
    week = 7 * 24
    assert api(student_a).post("/api/bookings/", booking_body(scope, 2, week)).status_code == 201
    r = api(student_a).post("/api/bookings/", booking_body(scope, 2 + week, week + 1))
    assert r.status_code == 400 and "7 天" in r.data["errors"]["end_at"][0]
    # maintenance (managers only) is not limited: repairs and calibration can take weeks
    assert api(manager).post("/api/bookings/", booking_body(scope, 2 + week, 30 * 24, kind="maintenance")).status_code == 201


def test_project_must_be_in_group(api, student_a, other_group, other_manager, scope):
    from projects.models import Project

    outside = Project.objects.create(group=other_group, name="外组项目", leader=other_manager)
    r = api(student_a).post("/api/bookings/", booking_body(scope, project_id=outside.id))
    assert r.status_code == 400 and "project_id" in r.data["errors"]


def test_cancel_rules(api, student_a, student_b, manager, scope):
    mine = book(scope, student_a, 2)
    assert api(student_b).post(f"/api/bookings/{mine.id}/cancel/").status_code == 403
    assert api(student_a).post(f"/api/bookings/{mine.id}/cancel/").data["cancelled_at"]
    assert api(student_a).post(f"/api/bookings/{mine.id}/cancel/").status_code == 409

    started = book(scope, student_a, -1, 2)
    assert api(student_a).post(f"/api/bookings/{started.id}/cancel/").status_code == 409
    assert api(manager).post(f"/api/bookings/{started.id}/cancel/").status_code == 200

    reported = book(scope, student_a, -5)
    UsageReport.objects.create(booking=reported, condition="normal")
    assert api(manager).post(f"/api/bookings/{reported.id}/cancel/").status_code == 409


def test_list_window_and_filters(api, student_a, student_b, group, scope):
    other = Equipment.objects.create(group=group, code="UT-002", name="第二台")
    book(scope, student_a, 2)
    book(other, student_b, 2)
    book(scope, student_b, 48)
    book(scope, student_a, 5, cancelled_at=timezone.now())
    window = {"from": at(0).isoformat(), "to": at(24).isoformat()}
    client = api(student_a)
    assert len(client.get("/api/bookings/", window).data) == 2
    assert [b["equipment"]["id"] for b in client.get("/api/bookings/", {**window, "equipment": scope.id}).data] == [scope.id]
    assert [b["user"]["id"] for b in client.get("/api/bookings/", {**window, "mine": 1}).data] == [student_a.id]
    assert client.get("/api/bookings/").status_code == 400
    assert client.get("/api/bookings/", {"from": at(0).isoformat(), "to": at(24 * 70).isoformat()}).status_code == 400
    assert client.get("/api/bookings/", {**window, "equipment": "x"}).status_code == 400


def test_in_use_and_recent_usage(api, student_a, student_b, scope):
    now_booking = book(scope, student_a, -1, 2)
    past = book(scope, student_b, -30)
    UsageReport.objects.create(booking=past, condition="abnormal", description="耦合剂漏")
    book(scope, student_b, 5)  # future: not "usage" yet
    data = api(student_a).get(f"/api/equipment/{scope.id}/").data
    assert data["in_use"] is True
    assert [b["id"] for b in data["recent_usage"]] == [now_booking.id, past.id]
    assert data["recent_usage"][1]["user"]["id"] == student_b.id
    assert data["recent_usage"][1]["report"]["condition"] == "abnormal"
    assert api(student_a).get("/api/equipment/").data["results"][0]["in_use"] is True


# --- usage reports ------------------------------------------------------------------------

def report(client, booking, **body):
    return client.post(f"/api/bookings/{booking.id}/report/", {"condition": "normal", **body}, format="multipart")


def test_abnormal_report_marks_equipment_for_check(api, student_a, manager, scope):
    booking = book(scope, student_a, -2)
    assert report(api(student_a), booking, condition="abnormal").status_code == 400  # description required
    r = report(api(student_a), booking, condition="abnormal", description="探头线断了")
    assert r.status_code == 201 and r.data["report"]["condition"] == "abnormal"
    scope.refresh_from_db()
    assert scope.status == "needs_check"
    assert "探头线断了" in scope.history.first().history_change_reason
    # Later bookings stay; new use bookings are refused until a manager sets it back to available.
    assert api(student_a).post("/api/bookings/", booking_body(scope)).status_code == 409
    dash = api(manager).get("/api/dashboard/").data
    assert [e["code"] for e in dash["manager"]["equipment_to_check"]] == ["UT-001"]


def test_report_rules(api, student_a, student_b, manager, scope):
    future = book(scope, student_a, 2)
    assert report(api(student_a), future).status_code == 409
    done = book(scope, student_a, -2)
    assert report(api(student_b), done).status_code == 403
    assert report(api(student_a), done).status_code == 201
    assert report(api(student_a), done).status_code == 409
    maintenance = book(scope, manager, -4, kind="maintenance")
    assert report(api(manager), maintenance).status_code == 409


def test_normal_report_keeps_status(api, student_a, scope):
    report(api(student_a), book(scope, student_a, -2))
    scope.refresh_from_db()
    assert scope.status == "available"


def test_photo_upload_and_scoped_download(api, student_a, student_b, other_manager, scope):
    booking = book(scope, student_a, -2)
    bad = SimpleUploadedFile("x.html", b"<script>")
    assert report(api(student_a), booking, photo=bad).status_code == 400
    photo = SimpleUploadedFile("现场.JPG", b"\xff\xd8fake-jpeg", content_type="image/jpeg")
    r = report(api(student_a), booking, condition="abnormal", description="外壳裂了", photo=photo)
    url = r.data["report"]["photo_url"]
    assert url == f"/api/bookings/{booking.id}/photo/"
    saved_report = UsageReport.objects.get(booking=booking)
    assert saved_report.photo_size == len(b"\xff\xd8fake-jpeg")
    assert saved_report.photo_uploaded_at is not None
    assert saved_report.photo_uploaded_at <= saved_report.reported_at
    stored = saved_report.photo.name
    assert stored.startswith("usage-photos/") and stored.endswith(".jpg") and "现场" not in stored
    download = api(student_b).get(url)
    assert download.status_code == 200 and b"".join(download.streaming_content) == b"\xff\xd8fake-jpeg"
    assert download["Content-Type"] == "image/jpeg"
    assert api(other_manager).get(url).status_code == 404
    no_photo = book(scope, student_b, -6)
    assert api(student_b).get(f"/api/bookings/{no_photo.id}/photo/").status_code == 404


def test_abnormal_report_mails_managers(api, settings, mailoutbox, django_capture_on_commit_callbacks, group, student_a, manager, scope):
    enable_mail()
    manager.email = "mgr@example.edu"
    manager.save()
    make_user("mgr_no_mail", group, "manager")
    with django_capture_on_commit_callbacks(execute=True):
        report(api(student_a), book(scope, student_a, -2), condition="abnormal", description="无回波")
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["mgr@example.edu"] and "UT-001" in mailoutbox[0].subject and "无回波" in mailoutbox[0].body


def test_no_mail_without_smtp(api, settings, mailoutbox, django_capture_on_commit_callbacks, student_a, manager, scope):
    manager.email = "mgr@example.edu"
    manager.save()
    with django_capture_on_commit_callbacks(execute=True):
        report(api(student_a), book(scope, student_a, -2), condition="abnormal", description="无回波")
    assert mailoutbox == []


class BrokenBackend:
    def __init__(self, *args, **kwargs):
        pass

    def send_messages(self, messages):
        raise OSError("SMTP unreachable")


def test_mail_failure_does_not_undo_the_report(api, settings, django_capture_on_commit_callbacks, student_a, manager, scope, caplog):
    enable_mail()
    settings.EMAIL_BACKEND = f"{__name__}.BrokenBackend"
    manager.email = "mgr@example.edu"
    manager.save()
    booking = book(scope, student_a, -2)
    with django_capture_on_commit_callbacks(execute=True):
        r = report(api(student_a), booking, condition="abnormal", description="无回波")
    assert r.status_code == 201
    assert UsageReport.objects.filter(booking=booking).exists()
    assert "邮件发送失败" in caplog.text


# --- workbench ----------------------------------------------------------------------------

def test_workbench_bookings(api, student_a, student_b, scope):
    upcoming = book(scope, student_a, 2)
    current = book(scope, student_a, -1, 2)
    unreported = book(scope, student_a, -5)
    reported = book(scope, student_a, -8)
    UsageReport.objects.create(booking=reported, condition="normal")
    book(scope, student_b, 4)
    book(scope, student_a, -10, kind="maintenance")
    book(scope, student_a, -15 * 24)  # ended more than 14 days ago: no longer shown
    my = api(student_a).get("/api/dashboard/").data["my"]
    assert [b["id"] for b in my["upcoming_bookings"]] == [current.id, upcoming.id]
    assert [b["id"] for b in my["unreported_bookings"]] == [unreported.id]
    assert api(student_a).get("/api/dashboard/").data["manager"] is None
