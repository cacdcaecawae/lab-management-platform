from django.db.models import Q
from rest_framework.exceptions import ValidationError

from .models import Achievement

FORMAL = (
    (Achievement.Type.PAPER, (Achievement.Status.ACCEPTED, Achievement.Status.PUBLISHED)),
    (Achievement.Type.PATENT, (Achievement.Status.GRANTED,)),
    (Achievement.Type.AWARD, (Achievement.Status.AWARDED,)),
    (Achievement.Type.SOFTWARE, (Achievement.Status.REGISTERED,)),
)


def filter_status(items, value):
    """Shared list/export/stats state contract; formal is specific to each outcome type."""
    if not value or value == "all":
        return items
    if value == "formal":
        condition = Q()
        for kind, statuses in FORMAL:
            condition |= Q(type=kind, status__in=statuses)
        return items.filter(condition)
    statuses = [s for s in value.split(",") if s]
    if not statuses or set(statuses) - set(Achievement.Status.values):
        raise ValidationError({"status": ["未知的状态"]})
    return items.filter(status__in=statuses)
