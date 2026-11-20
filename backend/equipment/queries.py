from datetime import timedelta

from django.utils import timezone

from .models import Equipment


CALIBRATION_REMINDER_DAYS = 30


def calibration_within(equipment, days=CALIBRATION_REMINDER_DAYS, today=None):
    """Include overdue devices, but not retired devices or devices without a due date."""
    today = today if today is not None else timezone.localdate()
    return equipment.exclude(status=Equipment.Status.RETIRED).filter(calibration_due__lte=today + timedelta(days=days))
