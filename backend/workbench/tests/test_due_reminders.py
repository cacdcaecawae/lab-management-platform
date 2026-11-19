import smtplib
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from io import StringIO
from threading import Event

import pytest
from django.core import mail as django_mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import close_old_connections
from django.utils import timezone

from conftest import enable_mail, make_user
from equipment.models import Equipment
from meetings.models import ActionItem, Meeting
from reports.models import WeeklyReport
from specimens.models import Defect, Specimen, SpecimenLoan
from workbench.models import ReminderDelivery


pytestmark = pytest.mark.django_db
MONDAY = date(2026, 11, 16)
FRIDAY = date(2026, 11, 20)


@pytest.fixture(autouse=True)
def known_shanghai_date(monkeypatch):
    # Thursday UTC is already Friday in Asia/Shanghai.
    monkeypatch.setattr(timezone, "now", lambda: datetime(2026, 11, 19, 16, 30, tzinfo=UTC))


def run(day=MONDAY, **kwargs):
    output = StringIO()
    call_command("send_due_reminders", date=day.isoformat(), stdout=output, **kwargs)
    return output.getvalue()


def address(user):
    user.email = f"{user.username}@example.test"
    user.save(update_fields=["email"])
    return user


def borrow(owner, code, due, *, lab=None, returned=False):
    specimen = Specimen.objects.create(group=lab or owner.group, code=code, name=code)
    return SpecimenLoan.objects.create(
        specimen=specimen, borrower=owner, due_date=due, returned_at=timezone.now() if returned else None,
    )


def test_groups_eligibility_blind_data_and_one_digest_per_day(student_a, manager, advisor, other_group, other_manager, monkeypatch):
    a, admin, other, _ = map(address, (student_a, manager, other_manager, advisor))
    monday = MONDAY
    first = borrow(a, "OWN-SECRET-SPECIMEN", monday - timedelta(days=2))
    Defect.objects.create(specimen=first.specimen, kind=Defect.Kind.CRACK, note="BLIND-TRUTH")
    borrow(other, "FOREIGN-ITEM", monday - timedelta(days=3))
    borrow(a, "OLD-RETURN", monday - timedelta(days=2), returned=True)
    borrow(a, "NOT-DUE", monday)
    borrow(a, "UNDATED", None)
    borrow(a, "MOVED-BORROWER", monday - timedelta(days=1), lab=other_group)
    address(make_user("inactive-manager", manager.group, manager.Role.MANAGER, is_active=False))
    for code, delta, status in (
        ("CAL-30", 30, Equipment.Status.AVAILABLE), ("CAL-7", 7, Equipment.Status.AVAILABLE),
        ("CAL-0", 0, Equipment.Status.AVAILABLE), ("CAL-NOT-YET", 8, Equipment.Status.AVAILABLE),
        ("CAL-RETIRED", 7, Equipment.Status.RETIRED),
    ):
        Equipment.objects.create(group=manager.group, code=code, name=code, status=status, calibration_due=monday + timedelta(days=delta))
    meeting = Meeting.objects.create(group=manager.group, created_by=manager, date=monday, title="组会")
    ActionItem.objects.create(meeting=meeting, owner=a, due_date=monday + timedelta(days=1), content="TOMORROW")
    ActionItem.objects.create(meeting=meeting, owner=a, due_date=monday - timedelta(days=1), content="YESTERDAY")
    ActionItem.objects.create(meeting=meeting, owner=a, due_date=monday + timedelta(days=1), content="DONE", done_at=timezone.now())
    ActionItem.objects.create(meeting=meeting, owner=a, due_date=monday, content="TODAY")
    ActionItem.objects.create(meeting=meeting, owner=other, due_date=monday + timedelta(days=1), content="MISMATCH")
    enable_mail()
    monkeypatch.setenv("SITE_URL", "https://lab.example.test/")
    run()
    by_target = {message.to[0]: message for message in django_mail.outbox}
    assert set(by_target) == {a.email, admin.email, other.email}
    own = by_target[a.email]
    assert "（3 项）" in own.subject
    assert "OWN-SECRET-SPECIMEN" in own.body and f"https://lab.example.test/specimens/{first.specimen_id}" in own.body
    assert "TOMORROW" in own.body and "YESTERDAY" in own.body
    assert not any(word in own.body for word in ["BLIND-TRUTH", "FOREIGN-ITEM", "MOVED-BORROWER", "OLD-RETURN", "NOT-DUE", "UNDATED", "DONE", "TODAY"])
    admin_body = by_target[admin.email].body
    assert all(word in admin_body for word in ["OWN-SECRET-SPECIMEN", "CAL-30", "CAL-7", "CAL-0"])
    assert not any(word in admin_body for word in ["FOREIGN-ITEM", "CAL-NOT-YET", "CAL-RETIRED", "MISMATCH"])
    assert "MISMATCH" not in by_target[other.email].body
    assert set(ReminderDelivery.objects.values_list("state", flat=True)) == {ReminderDelivery.State.SENT}
    run()
    assert len(django_mail.outbox) == 3


def test_friday_weekly_report_was_not_submitted_and_non_monday_overdue_rule(student_a, student_b, manager):
    a, b = address(student_a), address(student_b)
    address(manager)
    WeeklyReport.objects.create(owner=a, week_start=MONDAY, status=WeeklyReport.Status.SUBMITTED)
    borrow(a, "FIRST-OVERDUE", FRIDAY - timedelta(days=1))
    borrow(a, "SKIP-LONGER-OVERDUE", FRIDAY - timedelta(days=2))
    enable_mail()
    run(FRIDAY)
    by_target = {message.to[0]: message.body for message in django_mail.outbox}
    assert set(by_target) == {a.email, b.email}
    assert "FIRST-OVERDUE" in by_target[a.email] and "SKIP-LONGER-OVERDUE" not in by_target[a.email]
    assert "周报未交" not in by_target[a.email]
    assert "周报未交" in by_target[b.email]


def test_dry_run_disabled_and_input_validation(student_a, monkeypatch):
    a = address(student_a)
    borrow(a, "PREVIEW", MONDAY - timedelta(days=1))
    assert "跳过" in run()
    assert "PREVIEW" in run(dry_run=True)
    assert not ReminderDelivery.objects.exists()
    assert not django_mail.outbox
    monkeypatch.setenv("SITE_URL", "https://lab.example.test/path?key=not-real")
    with pytest.raises(CommandError, match="SITE_URL"):
        run(dry_run=True)
    with pytest.raises(CommandError, match="--date"):
        call_command("send_due_reminders", date="20261116", dry_run=True)


def test_future_day_is_preview_only(student_a):
    a = address(student_a)
    future = FRIDAY + timedelta(days=1)
    borrow(a, "FUTURE-PREVIEW", FRIDAY)
    enable_mail()
    with pytest.raises(CommandError, match="未来业务日期只能使用 --dry-run"):
        run(future)
    assert "FUTURE-PREVIEW" in run(future, dry_run=True)
    assert not django_mail.outbox
    assert not ReminderDelivery.objects.exists()


def test_temporary_refusal_retries_but_ambiguous_delivery_does_not(student_a, student_b, monkeypatch):
    a, b = address(student_a), address(student_b)
    borrow(a, "retry", MONDAY - timedelta(days=1))
    borrow(b, "ambiguous", MONDAY - timedelta(days=1))
    enable_mail()
    calls = []

    def fail_then_accept(subject, body, recipients):
        target = recipients[0]
        calls.append(target)
        if target == b.email:
            raise TimeoutError
        if calls.count(target) == 1:
            raise smtplib.SMTPDataError(451, b"try again")
        return True

    monkeypatch.setattr("workbench.management.commands.send_due_reminders.mail.send", fail_then_accept)
    with pytest.raises(CommandError, match="未确认"):
        run()
    with pytest.raises(CommandError, match="未确认"):
        run()
    delivery = ReminderDelivery.objects.get(recipient=a, day=MONDAY)
    assert (delivery.state, delivery.attempts) == (ReminderDelivery.State.SENT, 2)
    assert ReminderDelivery.objects.get(recipient=b, day=MONDAY).state == ReminderDelivery.State.UNCERTAIN
    assert calls == [a.email, b.email, a.email]


def test_retry_budget_and_permanent_refusal(student_a, student_b, monkeypatch):
    a, b = address(student_a), address(student_b)
    for user in (a, b):
        borrow(user, user.username, MONDAY - timedelta(days=1))
    enable_mail()

    def refuse(subject, body, recipients):
        target = recipients[0]
        raise smtplib.SMTPRecipientsRefused({target: (450 if target == a.email else 550, b"refused")})

    monkeypatch.setattr("workbench.management.commands.send_due_reminders.mail.send", refuse)
    for _ in range(5):
        with pytest.raises(CommandError, match="未确认"):
            run()
    a_row = ReminderDelivery.objects.get(recipient=a)
    assert (a_row.state, a_row.attempts) == (ReminderDelivery.State.FAILED, 3)
    b_row = ReminderDelivery.objects.get(recipient=b)
    assert (b_row.state, b_row.attempts) == (ReminderDelivery.State.FAILED, 1)


@pytest.mark.django_db(transaction=True)
def test_parallel_runs_claim_one_delivery(student_a, monkeypatch):
    a = address(student_a)
    borrow(a, "parallel", MONDAY - timedelta(days=1))
    enable_mail()
    sending, release = Event(), Event()
    calls = []

    def transport(subject, body, recipients):
        calls.extend(recipients)
        sending.set()
        assert release.wait(10)
        return True

    def first():
        close_old_connections()
        try:
            return run()
        finally:
            close_old_connections()

    monkeypatch.setattr("workbench.management.commands.send_due_reminders.mail.send", transport)
    with ThreadPoolExecutor(max_workers=1) as pool:
        original = pool.submit(first)
        try:
            assert sending.wait(10)
            with pytest.raises(CommandError, match="未确认"):
                run()
        finally:
            release.set()
        assert "sent=1" in original.result(timeout=10)
    assert calls == [a.email]
