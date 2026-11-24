from datetime import timedelta

from django.utils import timezone

from .models import Booking, Equipment


CALIBRATION_REMINDER_DAYS = 30
UNREPORTED_DAYS = timedelta(days=14)  # older use bookings without a usage report are no longer worth a reminder


def awaiting_report(bookings, now, ongoing=False):
    """Use bookings without a usage report that ended in the last UNREPORTED_DAYS; with ongoing, also those under
    way (they can be reported once started). The workbench and the bookings list use the same rule."""
    started = {"start_at__lte": now} if ongoing else {"end_at__lte": now}
    return bookings.filter(
        kind=Booking.Kind.USE, cancelled_at__isnull=True, end_at__gt=now - UNREPORTED_DAYS, report__isnull=True, **started
    )


def calibration_within(equipment, days=CALIBRATION_REMINDER_DAYS, today=None):
    """Include overdue devices, but not retired devices or devices without a due date."""
    today = today if today is not None else timezone.localdate()
    return equipment.exclude(status=Equipment.Status.RETIRED).filter(calibration_due__lte=today + timedelta(days=days))
