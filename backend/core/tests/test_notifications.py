from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone

from conftest import make_user
from core.models import Notification
from core.notifications import notify
from equipment.models import Booking, Equipment
from meetings.models import Meeting
from procurement.models import Fund, PurchaseRequest
from reports.models import WeeklyReport
from reports.queries import current_week_start
from specimens.models import Specimen, SpecimenLoan


pytestmark = pytest.mark.django_db
URL = "/api/notifications/"


def notices(user):
    return list(Notification.objects.filter(recipient=user).order_by("id").values_list("title", "link"))


def test_scope_listing_read_all_and_group_role_changes(api, group, other_group, student_a, student_b, manager, other_manager, ops):
    notify(group.pk, "待初审", "/purchases/3", role="manager")
    notify(group.pk, "更新", "/meetings/2", recipient_ids=[student_a.pk, student_b.pk, other_manager.pk])
    a = api(student_a)
    assert api().get(URL).status_code == api(ops).get(URL).status_code == 403
    assert a.get(URL + "unread-count/").json() == {"count": 1}
    item = a.get(URL).json()["results"][0]
    assert set(item) == {"id", "title", "body", "link", "created_at", "read_at"}
    for user in (student_b, manager, other_manager):
        assert api(user).post(URL + f"{item['id']}/read/").status_code == 404
    assert a.post(URL + f"{item['id']}/read/").json()["read_at"]
    assert a.get(URL + "?unread=1").json()["count"] == 0
    assert a.post(URL + "read-all/").json() == {"updated": 0}
    assert api(student_b).post(URL + "read-all/").json() == {"updated": 1}
    assert a.get(URL).json()["count"] == 1
    manager.role = manager.Role.STUDENT
    manager.save(update_fields=["role"])
    assert api(manager).get(URL).json()["count"] == 0
    student_a.group = other_group
    student_a.save(update_fields=["group"])
    assert api(student_a).get(URL).json()["count"] == 0


def test_creation_scope_and_rollback(group, student_a, other_manager):
    inactive = make_user("retired-manager", group, role=other_manager.Role.MANAGER, is_active=False)
    with pytest.raises(ValueError, match="local"):
        notify(group.pk, "bad path", "https://example.test/", recipient_ids=[student_a.pk])
    with pytest.raises(ValueError, match="recipients"):
        notify(group.pk, "bad audience", "/equipment/1")
    notify(group.pk, "a", "/equipment/1", recipient_ids=[inactive.pk, other_manager.pk])
    assert not Notification.objects.exists()
    with pytest.raises(RuntimeError), transaction.atomic():
        notify(group.pk, "rollback", "/equipment/1", recipient_ids=[student_a.pk])
        assert Notification.objects.filter(recipient=student_a).exists()
        raise RuntimeError("test rollback")
    assert not Notification.objects.exists()


def test_purge_preserves_unread_and_recent(group, student_a):
    records = [
        Notification.objects.create(recipient=student_a, group=group, title=str(i), link="/equipment/1", read_at=read)
        for i, read in enumerate([timezone.now() - timedelta(days=181), timezone.now() - timedelta(days=179), None])
    ]
    output = StringIO()
    call_command("purge_notifications", dry_run=True, stdout=output)
    assert "1" in output.getvalue() and Notification.objects.count() == 3
    call_command("purge_notifications", stdout=StringIO())
    assert set(Notification.objects.values_list("pk", flat=True)) == {r.pk for r in records[1:]}


def test_purchase_notifications_for_each_transition(api, student_a, manager, advisor, group, other_manager):
    student, admin, teacher = api(student_a), api(manager), api(advisor)
    fund = Fund.objects.create(group=group, code="TEST", name="Test")
    created = student.post("/api/purchases/", {
        "purpose": "fixture", "fund_id": fund.pk,
        "items": [{"name": "fixture", "quantity": 1, "unit_price": "1.00"}],
    }, format="json")
    assert created.status_code == 201
    path = f"/purchases/{created.json()['id']}"
    endpoint = f"/api{path}"

    def review(client, verdict="approve"):
        p = PurchaseRequest.objects.get(pk=created.json()["id"])
        body = {"verdict": verdict, "comment": "fixture", "status_seen": p.status, "total_seen": "1.00",
                "submitted_seen": p.submitted_at.isoformat()}
        return client.post(endpoint + "/review/", body, format="json")

    assert student.post(endpoint + "/submit/").status_code == 200
    assert review(admin, "return").status_code == 200
    assert student.post(endpoint + "/submit/").status_code == 200
    assert review(admin).status_code == 200
    assert review(teacher).status_code == 200
    assert admin.post(endpoint + "/purchased/").status_code == 200
    assert admin.post(endpoint + "/arrived/").status_code == 200
    assert notices(student_a) == [(title, path) for title in ("采购申请退回修改", "采购申请已批准", "采购申请已到货")]
    assert notices(manager) == [("采购申请待初审", path)] * 2
    assert notices(advisor) == [("采购申请待终审", path)]
    assert notices(other_manager) == []


def test_equipment_notification_is_atomic_and_rolls_back_business_write(api, group, student_a, manager, other_manager, monkeypatch):
    device = Equipment.objects.create(group=group, code="T", name="T")
    start = timezone.now() - timedelta(hours=2)
    booking = Booking.objects.create(equipment=device, user=student_a, start_at=start, end_at=start + timedelta(hours=1))
    endpoint = f"/api/bookings/{booking.pk}/report/"
    send = notify

    def write_then_fail(*args, **kwargs):
        send(*args, **kwargs)
        raise RuntimeError("notification failure")

    with monkeypatch.context() as patch:
        patch.setattr("equipment.views.notify", write_then_fail)
        with pytest.raises(RuntimeError, match="notification failure"):
            api(student_a).post(endpoint, {"condition": "abnormal", "description": "fixture"})
    device.refresh_from_db()
    assert device.status == Equipment.Status.AVAILABLE and not Notification.objects.exists()
    assert not hasattr(booking, "report")
    assert api(student_a).post(endpoint, {"condition": "abnormal", "description": "fixture"}).status_code == 201
    assert notices(manager) == [("设备登记使用异常", f"/equipment/{device.pk}")]
    assert notices(other_manager) == []


def test_meeting_assignment_and_reassignment_report_review_and_specimen_return(api, group, manager, student_a, student_b):
    admin = api(manager)
    meeting = admin.post("/api/meetings/", {
        "date": "2026-11-19", "title": "Fixture", "actions": [{"owner_id": student_a.pk, "content": "fixture"}],
    }, format="json")
    assert meeting.status_code == 201
    path = f"/meetings/{meeting.json()['id']}"
    aid = meeting.json()["actions"][0]["id"]
    assert admin.patch(f"/api{path}/", {"actions": [{"id": aid, "content": "edited"}]}, format="json").status_code == 200
    assert admin.patch(f"/api{path}/", {"actions": [{"id": aid, "owner_id": student_b.pk}]}, format="json").status_code == 200
    assert notices(student_a) == [("有新的组会行动项分配给你", path)]
    assert notices(student_b) == [("有新的组会行动项分配给你", path)]

    report = WeeklyReport.objects.create(owner=student_a, week_start=current_week_start(), status=WeeklyReport.Status.SUBMITTED)
    feedback = f"/api/reports/{report.pk}/feedback/"
    assert admin.post(feedback, {"verdict": "needs_revision", "content": "补充"}, format="json").status_code == 200
    assert api(student_a).post(f"/api/reports/{report.pk}/submit/").status_code == 200
    assert admin.post(feedback, {"verdict": "reviewed", "content": "已阅"}, format="json").status_code == 200
    assert notices(student_a)[1:] == [(title, f"/reports/{report.pk}") for title in ("周报需补充", "周报已阅")]

    specimen = Specimen.objects.create(group=group, code="NOTICE", name="试件")
    loan = SpecimenLoan.objects.create(specimen=specimen, borrower=student_a)
    endpoint = f"/api/specimens/{specimen.pk}/return/"
    assert admin.post(endpoint, {"loan_id_seen": loan.pk}, format="json").status_code == 200
    assert notices(student_a)[-1] == ("管理员已登记试件归还", f"/specimens/{specimen.pk}")
    own = SpecimenLoan.objects.create(specimen=specimen, borrower=student_a)
    assert api(student_a).post(endpoint, {"loan_id_seen": own.pk}, format="json").status_code == 200
    assert len(notices(student_a)) == 4
