"""Rollback must clean only the newly uploaded photo, not an already committed report."""
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.utils import timezone

from equipment.models import Booking, Equipment, UsageReport

pytestmark = pytest.mark.django_db(transaction=True)


def setup_booking(group, student_a):
    equipment = Equipment.objects.create(group=group, code="PHOTO", name="Photo test")
    now = timezone.now()
    booking = Booking.objects.create(equipment=equipment, user=student_a, start_at=now, end_at=now + timezone.timedelta(hours=1))
    return booking


def send_photo(api, user, booking, abnormal=False):
    return api(user).post(f"/api/bookings/{booking.pk}/report/", {
        "condition": "abnormal" if abnormal else "normal",
        "description": "broken" if abnormal else "",
        "photo": SimpleUploadedFile("photo.jpg", b"test-photo", content_type="image/jpeg"),
    }, format="multipart")


def files(settings):
    return list(Path(settings.MEDIA_ROOT).rglob("*.jpg"))


@pytest.mark.parametrize("failure", ["insert", "equipment"])
def test_photo_removed_on_report_rollback(api, student_a, group, settings, failure):
    booking = setup_booking(group, student_a)
    if failure == "insert":
        original = UsageReport._do_insert

        def insert_then_fail(self, *args, **kwargs):
            original(self, *args, **kwargs)  # FileField has written before INSERT; then roll back.
            raise IntegrityError("injected insert failure")

        target = patch.object(UsageReport, "_do_insert", insert_then_fail)
    else:
        target = patch.object(Equipment, "save", side_effect=IntegrityError("injected equipment failure"))
    with target, pytest.raises(IntegrityError, match="injected"):
        send_photo(api, student_a, booking, abnormal=True)
    assert not UsageReport.objects.filter(booking=booking).exists()
    assert files(settings) == []
    booking.equipment.refresh_from_db()
    assert booking.equipment.status == Equipment.Status.AVAILABLE


def test_cleanup_error_preserves_original_exception(api, student_a, group, settings, caplog):
    booking = setup_booking(group, student_a)
    storage = UsageReport._meta.get_field("photo").storage
    with patch.object(Equipment, "save", side_effect=IntegrityError("original failure")), patch.object(
        storage, "delete", side_effect=OSError("storage unavailable")
    ), pytest.raises(IntegrityError, match="original failure"):
        send_photo(api, student_a, booking, abnormal=True)
    assert not UsageReport.objects.filter(booking=booking).exists()
    assert "Failed to clean up rolled-back usage photo" in caplog.text
    assert len(files(settings)) == 1  # logged orphan; never mask the primary error


def test_notification_error_keeps_committed_photo(api, student_a, group, settings):
    booking = setup_booking(group, student_a)
    with patch("equipment.views.notify_managers", side_effect=RuntimeError("after commit")), pytest.raises(RuntimeError):
        send_photo(api, student_a, booking, abnormal=True)
    saved = UsageReport.objects.get(booking=booking)
    assert saved.photo.storage.exists(saved.photo.name)
    assert len(files(settings)) == 1


def test_success_and_duplicate_keep_existing_photo(api, student_a, group, settings):
    booking = setup_booking(group, student_a)
    assert send_photo(api, student_a, booking).status_code == 201
    saved = UsageReport.objects.get(booking=booking)
    original_name = saved.photo.name
    assert send_photo(api, student_a, booking).status_code == 409
    saved.refresh_from_db()
    assert saved.photo.name == original_name and saved.photo.storage.exists(original_name)
    assert len(files(settings)) == 1
