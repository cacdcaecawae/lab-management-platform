"""Issue #48 N6: the new notifications, the workbench's new to-dos and the notification center's module filter."""
import datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from conftest import make_user
from core.models import Notification
from equipment.models import Booking, Equipment
from inventory.models import Batch, Consumable, StockTxn
from procurement.models import Fund, PurchaseRequest, Reimbursement
from projects.models import Task
from reports.models import WeeklyReport
from workbench.reminders import build_digests

pytestmark = pytest.mark.django_db


def titles(user):
    return list(Notification.objects.filter(recipient=user).order_by("id").values_list("title", flat=True))


def test_task_assignment_and_presenter(api, project, student_a, student_b, manager):
    client = api(student_a)
    created = client.post(f"/api/projects/{project.pk}/tasks/", {"title": "标定", "assignee_id": student_b.pk}, format="json")
    assert created.status_code == 201, created.data
    assert titles(student_b) == ["有任务分配给你"]
    client.post(f"/api/projects/{project.pk}/tasks/", {"title": "自己的", "assignee_id": student_a.pk}, format="json")
    assert titles(student_a) == []  # took it themselves
    api(student_b).patch(f"/api/tasks/{created.data['id']}/", {"title": "改名"}, format="json")
    assert titles(student_b) == ["有任务分配给你"]  # still theirs: no second notice
    meeting = {"date": "2026-11-16", "agenda": [{"presenter_id": student_a.pk, "topic": "成像"}], "actions": []}
    pk = api(manager).post("/api/meetings/", meeting, format="json").data["id"]
    assert titles(student_a) == ["你在组会上有汇报"]
    api(manager).patch(f"/api/meetings/{pk}/", {"agenda": [
        {"presenter_id": student_a.pk, "topic": "成像"}, {"presenter_id": student_b.pk, "topic": "算法"},
    ]}, format="json")
    assert titles(student_a) == ["你在组会上有汇报"] and titles(student_b)[-1] == "你在组会上有汇报"


def test_report_submitted_reaches_the_advisors(api, group, student_a, manager, advisor):
    report = WeeklyReport.objects.create(owner=student_a, week_start=datetime.date(2026, 11, 16), goals="x", done="x")
    assert api(student_a).post(f"/api/reports/{report.pk}/submit/").status_code == 200
    assert titles(advisor) == ["有新的周报待反馈"] and titles(manager) == []
    assert Notification.objects.get(recipient=advisor).body == "s_a · 2026-11-16 这一周"


def test_reimbursement_paid_or_returned_tells_the_owner(api, group, student_a, manager):
    fund = Fund.objects.create(group=group, code="F", name="面上")
    bill = Reimbursement.objects.create(owner=student_a, fund=fund, amount=Decimal("9.00"), occurred_on=datetime.date(2026, 11, 2),
                                        status=Reimbursement.Status.SUBMITTED, description="打车")
    assert api(manager).post(f"/api/reimbursements/{bill.pk}/advance/", {"status": "pending"}).status_code == 200
    assert titles(student_a) == ["报销被退回待提交"]
    Reimbursement.objects.filter(pk=bill.pk).update(status=Reimbursement.Status.SUBMITTED)
    assert api(manager).post(f"/api/reimbursements/{bill.pk}/advance/", {"status": "paid"}).status_code == 200
    assert titles(student_a)[-1] == "报销已到账"


def test_manager_cancelling_a_booking_tells_the_booker(api, group, student_a, manager):
    device = Equipment.objects.create(group=group, code="UT", name="探伤仪")
    start = timezone.now() + datetime.timedelta(days=1)
    mine = Booking.objects.create(equipment=device, user=student_a, start_at=start, end_at=start + datetime.timedelta(hours=1))
    theirs = Booking.objects.create(equipment=device, user=student_a, start_at=start + datetime.timedelta(hours=2),
                                    end_at=start + datetime.timedelta(hours=3))
    api(student_a).post(f"/api/bookings/{mine.pk}/cancel/")
    assert titles(student_a) == []
    api(manager).post(f"/api/bookings/{theirs.pk}/cancel/")
    assert titles(student_a) == ["你的设备预约被管理员取消"]


def test_low_stock_is_said_once_per_fall(api, group, student_a, manager, advisor):
    gel = Consumable.objects.create(group=group, name="耦合剂", safety_stock=3)
    StockTxn.objects.create(consumable=gel, kind=StockTxn.Kind.IN, quantity=5, handler=manager)
    url = f"/api/consumables/{gel.pk}/txns/"
    take = lambda n: api(student_a).post(url, {"kind": "out", "quantity": n}, format="json")  # noqa: E731
    assert take(1).status_code == 201  # 4: still above
    assert titles(manager) == []
    take(2)  # 2: below
    take(1)  # 1: still below, no second notice
    assert titles(manager) == ["耗材低于安全库存"] and titles(advisor) == []
    api(manager).post(url, {"kind": "in", "quantity": 5}, format="json")  # 6: restocked
    take(4)  # 2: below again
    assert titles(manager) == ["耗材低于安全库存", "耗材低于安全库存"]
    assert take(10).status_code == 400 and len(titles(manager)) == 2  # refused: nothing written


def test_workbench_todos(api, group, project, student_a, manager, advisor):
    from procurement.models import Attachment  # noqa: PLC0415

    fund = Fund.objects.create(group=group, code="F", name="面上")
    PurchaseRequest.objects.create(owner=student_a, fund=fund, purpose="草稿")
    bought = PurchaseRequest.objects.create(owner=student_a, fund=fund, purpose="已批准", status=PurchaseRequest.Status.APPROVED)
    no_invoice = Reimbursement.objects.create(owner=student_a, fund=fund, amount=1, occurred_on=datetime.date(2026, 11, 2))
    has_invoice = Reimbursement.objects.create(owner=student_a, fund=fund, amount=1, occurred_on=datetime.date(2026, 11, 3))
    Attachment.objects.create(reimbursement=has_invoice, kind=Attachment.Kind.INVOICE, name="i.pdf", size=1, uploaded_by=student_a)
    make_user("signup", group, is_active=False, pending=True)
    Task.objects.create(project=project, title="逾期", created_by=student_a, due_date=datetime.date(2020, 1, 1))
    mine = api(student_a).get("/api/dashboard/").data
    assert [p["purpose"] for p in mine["my"]["draft_purchases"]] == ["草稿"]
    assert [r["id"] for r in mine["my"]["reimbursements_without_invoice"]] == [no_invoice.pk]
    assert "overdue_tasks" not in mine
    managing = api(manager).get("/api/dashboard/").data
    assert [u["name"] for u in managing["manager"]["pending_signups"]] == ["signup"]
    assert [p["id"] for p in managing["manager"]["to_purchase"]] == [bought.pk]
    assert managing["overdue_tasks"] == 1 and api(advisor).get("/api/dashboard/").data["overdue_tasks"] == 1


def test_notification_center_by_module(api, group, student_a):
    for link in ("/reports/1", "/meetings/2", "/purchases/3", "/equipment/4"):
        Notification.objects.create(recipient=student_a, group=group, title=link, link=link)
    client = api(student_a)
    assert [n["link"] for n in client.get("/api/notifications/", {"module": "reports"}).data["results"]] == ["/meetings/2", "/reports/1"]
    assert client.get("/api/notifications/", {"module": "money"}).data["count"] == 1
    assert client.get("/api/notifications/", {"module": "nope"}).data["count"] == 0


def test_daily_mail_lists_batches_expiring_on_the_reminder_days(group, manager):
    manager.email = "m@example.com"
    manager.save()
    today = datetime.date(2026, 11, 23)
    gel = Consumable.objects.create(group=group, name="耦合剂", unit="瓶", tracks_batches=True)
    soon = Batch.objects.create(consumable=gel, batch_no="A1", expires_on=today + datetime.timedelta(days=7))
    StockTxn.objects.create(consumable=gel, batch=soon, kind=StockTxn.Kind.IN, quantity=2, handler=manager)
    Batch.objects.create(consumable=gel, batch_no="B2", expires_on=today)  # no stock: not mentioned
    digests = {user.pk: body for user, _count, body in build_digests(today, "https://lab")}
    assert "耗材批次到期" in digests[manager.pk] and "A1" in digests[manager.pk] and "B2" not in digests[manager.pk]
