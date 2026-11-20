from django.utils import timezone

from core.permissions import scope_group

from .models import SpecimenLoan


def open_loans():
    return SpecimenLoan.objects.filter(returned_at__isnull=True)


def group_open_loans(user):
    return scope_group(open_loans(), user, group_field="specimen__group")


def overdue_loans(loans, today=None):
    """An open loan is overdue on the day after its due date, never on the due date."""
    return loans.filter(due_date__lt=today if today is not None else timezone.localdate())
