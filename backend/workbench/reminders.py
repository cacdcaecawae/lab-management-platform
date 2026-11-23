"""The daily digest is a read-side aggregation, not a business workflow."""

from collections import defaultdict
from datetime import timedelta

from django.db.models import F

from accounts.models import User
from equipment.models import Equipment
from equipment.queries import CALIBRATION_REMINDER_DAYS, calibration_within
from meetings.models import ActionItem
from reports.models import WeeklyReport
from reports.queries import HANDED_IN
from specimens.queries import open_loans, overdue_loans


def build_digests(today, site_url):
    dates = {today + timedelta(days=days) for days in (0, 7, CALIBRATION_REMINDER_DAYS)}
    yesterday, tomorrow = today - timedelta(days=1), today + timedelta(days=1)
    monday = today.weekday() == 0
    members = list(User.objects.filter(is_active=True, group__isnull=False).exclude(email="").order_by("pk"))
    eligible = {user.pk: user for user in members if user.email.strip()}
    managers = defaultdict(list)
    digests = defaultdict(list)
    for user in eligible.values():
        if user.is_manager:
            managers[user.group_id].append(user.pk)

    def notice(recipient, title, item, path):
        if recipient in eligible:
            digests[recipient].append((title, f"{item}  {site_url}{path}"))

    overdue = overdue_loans(open_loans(), today=today).select_related("specimen", "borrower").order_by("due_date", "id")
    for loan in overdue if monday else overdue.filter(due_date=yesterday):
        specimen = loan.specimen
        label = f"{specimen.code} {specimen.name}（{loan.due_date} 到期）"
        path = f"/specimens/{specimen.pk}"
        group_managers = managers[specimen.group_id] if monday else ()
        if loan.borrower.group_id == specimen.group_id and loan.borrower_id not in group_managers:
            notice(loan.borrower_id, "试件逾期未还", label, path)
        for manager_id in group_managers:
            borrower = loan.borrower.display_name if loan.borrower.group_id == specimen.group_id else "已离组"
            notice(manager_id, "本组逾期未还", f"{label} · {borrower}", path)

    for device in calibration_within(Equipment.objects.filter(calibration_due__in=dates), today=today).order_by("calibration_due", "id"):
        for manager_id in managers[device.group_id]:
            notice(manager_id, "设备校准", f"{device.code} {device.name}（{device.calibration_due} 到期）", f"/equipment/{device.pk}")

    actions = ActionItem.objects.filter(
        owner_id__in=eligible,
        owner__group_id=F("meeting__group_id"),
        done_at__isnull=True,
        due_date__in=[yesterday, tomorrow],
    ).order_by("due_date", "id")
    for item in actions:
        notice(item.owner_id, "组会行动项", f"{item.content}（{item.due_date} 到期）", f"/meetings/{item.meeting_id}")

    if today.weekday() == 4:
        week_start = today - timedelta(days=4)
        submitted = WeeklyReport.objects.filter(
            owner_id__in=eligible, week_start=week_start, status__in=HANDED_IN,
        ).values_list("owner_id", flat=True)
        submitted = set(submitted)
        for user in eligible.values():
            if user.role == User.Role.STUDENT and user.pk not in submitted:
                notice(user.pk, "周报未交", "尚未提交本周周报。", "/reports")

    for pk, items in sorted(digests.items()):
        sections = defaultdict(list)
        for heading, line in items:
            sections[heading].append(f"- {line}")
        body = "\n\n".join(f"{heading}\n" + "\n".join(lines) for heading, lines in sections.items())
        yield eligible[pk], len(items), body
