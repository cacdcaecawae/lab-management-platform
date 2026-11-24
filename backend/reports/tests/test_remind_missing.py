"""Issue #48 N4: the advisor reminds the students who have not handed in a week's report, at most once a day."""
import datetime

import pytest
from django.core import mail as django_mail

from conftest import enable_mail
from core.models import Notification
from reports.models import WeeklyReport

pytestmark = pytest.mark.django_db
WEEK = datetime.date(2026, 11, 16)


def test_reminds_the_missing_once_a_day(api, group, student_a, student_b, manager, advisor):
    enable_mail()
    student_b.email = "b@example.com"
    student_b.save()
    WeeklyReport.objects.create(owner=student_a, week_start=WEEK, status=WeeklyReport.Status.SUBMITTED)
    client = api(advisor)
    first = client.post("/api/reports/remind-missing/", {"week_start": "2026-11-16"}, format="json")
    assert first.status_code == 200, first.data
    assert first.data == {"reminded": 2, "already": 0}  # student_b and the student manager
    title = "请提交 2026-11-16 这一周的周报"
    assert set(Notification.objects.filter(title=title).values_list("recipient_id", flat=True)) == {student_b.pk, manager.pk}
    assert len(django_mail.outbox) == 1
    assert django_mail.outbox[0].to == [] and django_mail.outbox[0].bcc == ["b@example.com"]
    again = client.post("/api/reports/remind-missing/", {"week_start": "2026-11-16"}, format="json")
    assert again.data == {"reminded": 0, "already": 2}
    assert Notification.objects.filter(title=title).count() == 2


def test_only_advisors_remind(api, student_a, manager):
    assert api(manager).post("/api/reports/remind-missing/", {}, format="json").status_code == 403
    assert api(student_a).post("/api/reports/remind-missing/", {"week_start": "2026-11-17"}, format="json").status_code == 403
