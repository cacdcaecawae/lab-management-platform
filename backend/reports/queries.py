"""Weekly report queries shared by the report pages and the workbench."""

from datetime import timedelta

from django.utils import timezone

from accounts.models import User
from core.permissions import scope_group

from .models import WeeklyReport

Status = WeeklyReport.Status
HANDED_IN = (Status.SUBMITTED, Status.NEEDS_REVISION, Status.REVIEWED)


def current_week_start():
    today = timezone.localdate()
    return today - timedelta(days=today.weekday())


def missing_students(user, week_start):
    """Active students in the user's group without a handed-in report for that week."""
    handed_in = WeeklyReport.objects.filter(week_start=week_start, status__in=HANDED_IN).values("owner_id")
    students = scope_group(User.objects.filter(role=User.Role.STUDENT, is_active=True), user)
    return students.exclude(pk__in=handed_in).order_by("username")
