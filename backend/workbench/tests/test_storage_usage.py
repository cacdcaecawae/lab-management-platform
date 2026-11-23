from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from accounts.models import User
from achievements.models import Achievement
from datasets.models import DataFile, Dataset
from equipment.models import Booking, Equipment, UsageReport
from projects.models import Project
from workbench import storage

pytestmark = pytest.mark.django_db
OPS = "/api/system/storage/"
GROUP = "/api/storage-usage/"


def test_storage_metrics_and_scope(api, group, manager, advisor, student_a, other_manager, monkeypatch):
    ops = User.objects.create(username="ops-storage", is_superuser=True, must_change_password=False)
    project = Project.objects.create(group=group, name="合成项目", leader=student_a)
    data = Dataset.objects.create(owner=student_a, project=project, name="合成数据集")
    outsider = Dataset.objects.create(owner=other_manager, project=project, name="外部合成")
    monkeypatch.setattr(storage.timezone, "now", lambda: datetime(2026, 11, 20, tzinfo=timezone.utc))
    for month, day, hour, size in ((7, 31, 16, 100), (8, 31, 16, 200), (9, 30, 16, 300)):
        f = DataFile.objects.create(dataset=data, name=f"{size}.dat", file=f"synthetic/{size}", size=size, uploaded_by=student_a)
        DataFile.objects.filter(pk=f.pk).update(uploaded_at=datetime(2026, month, day, hour, tzinfo=timezone.utc))
    DataFile.objects.create(dataset=outsider, name="external", file="synthetic/external", size=999, uploaded_by=other_manager)
    DataFile.objects.create(dataset=data, name="cross", file="synthetic/cross", size=1, uploaded_by=other_manager)
    Achievement.objects.create(group=group, title="合成", type="paper", status="published",
                               date="2026-11-01", fulltext="synthetic/paper", created_by=manager)
    equipment = Equipment.objects.create(group=group, code="E", name="合成设备")
    for day, size in ((1, None), (2, 8)):
        booking = Booking.objects.create(equipment=equipment, user=student_a,
            start_at=datetime(2026, 11, day, 4, tzinfo=timezone.utc), end_at=datetime(2026, 11, day, 5, tzinfo=timezone.utc))
        UsageReport.objects.create(booking=booking, condition="normal", photo=f"synthetic/photo-{day}", photo_size=size)
    disk_usage = Mock(return_value=(1000, 900, 100))
    monkeypatch.setattr(storage.shutil, "disk_usage", disk_usage)
    r = api(ops).get(OPS)
    assert r.status_code == 200
    assert r.data["disk"]["filesystem"]["free_bytes"] == 100
    report = next(g for g in r.data["groups"] if g["id"] == group.pk)
    assert report["known_bytes"] == 609
    assert report["unknown_files"] == 2
    assert report["modules"]["equipment"] == {"known_bytes": 8, "unknown_files": 1}
    assert report["modules"]["achievements"] == {"known_bytes": 0, "unknown_files": 1}
    assert [(month, report["months"][month]) for month in ("2026-08", "2026-09", "2026-10")] == [
        ("2026-08", 100), ("2026-09", 200), ("2026-10", 300)]
    assert r.data["projection"]["annual_retained_known_bytes"] == 2400
    assert api(manager).get(OPS).status_code == 403
    assert api(student_a).get(GROUP).status_code == 403
    assert api(ops).get(GROUP).status_code == 403
    result = api(advisor).get(GROUP).data
    assert {row["id"]: row["known_bytes"] for row in result["by_member"]} == {student_a.pk: 600, None: 1}
    assert {row["id"]: row["known_bytes"] for row in result["by_project"]} == {project.pk: 601}
    assert all(r["id"] is None for r in api(other_manager).get(GROUP).data["by_project"])
    monkeypatch.setattr(storage, "default_storage", object())
    disk_usage.reset_mock()
    assert api(ops).get(OPS).data["disk"] == {"kind": "non_local", "filesystem": None}
    disk_usage.assert_not_called()
    DataFile.objects.filter(size=200).delete()
    assert api(ops).get(OPS).data["projection"] is None


def test_all_recorded_attachment_sources(api, group, manager, other_manager, monkeypatch):
    from knowledge.models import Doc, DocVersion
    from meetings.models import Meeting, MeetingFile
    from procurement.models import Attachment, Fund, PurchaseRequest, Reimbursement
    from specimens.models import Specimen, SpecimenLoan

    ops = User.objects.create(username="ops-metadata", is_superuser=True, must_change_password=False)
    monkeypatch.setattr(storage.shutil, "disk_usage", Mock(side_effect=FileNotFoundError))
    doc = Doc.objects.create(group=group, title="版本验证", author=manager)
    for number, size in ((1, 4), (2, 0)):
        DocVersion.objects.create(doc=doc, number=number, file=f"synthetic/version-{number}",
                                  name="sample", size=size, uploaded_by=other_manager)
    meeting = Meeting.objects.create(group=group, date="2026-11-01", created_by=manager)
    MeetingFile.objects.create(meeting=meeting, file="synthetic/meeting", name="sample", size=5, uploaded_by=manager)
    purchase = PurchaseRequest.objects.create(owner=manager)
    fund = Fund.objects.create(group=other_manager.group, name="合成经费")
    pay = Reimbursement.objects.create(owner=other_manager, fund=fund, amount="1", occurred_on="2026-11-01")
    Attachment.objects.create(purchase=purchase, file="synthetic/purchase", size=6, uploaded_by=other_manager)
    Attachment.objects.create(reimbursement=pay, file="synthetic/reimbursement", size=7, uploaded_by=manager)
    specimen = Specimen.objects.create(group=group, code="SP-ST", name="合成试件")
    SpecimenLoan.objects.create(
        specimen=specimen, borrower=manager, return_photo="synthetic/specimen.jpg",
        return_photo_size=9, return_photo_uploaded_at=datetime(2026, 11, 1, 4, tzinfo=timezone.utc),
    )
    r = api(ops).get(OPS)
    assert r.data["disk"] == {"kind": "local", "filesystem": None}
    by_group = {g["id"]: g for g in r.data["groups"]}
    ours = by_group[group.pk]
    assert ours["known_bytes"] == 24 and ours["unknown_files"] == 0
    assert ours["modules"]["knowledge"]["known_bytes"] == 4
    assert ours["modules"]["meetings"]["known_bytes"] == 5
    assert ours["modules"]["procurement"]["known_bytes"] == 6
    assert ours["modules"]["specimens"]["known_bytes"] == 9
    assert by_group[other_manager.group_id]["modules"]["procurement"]["known_bytes"] == 7


def test_admin_photo_replacement_clear_and_unchanged(tmp_path, settings, group, student_a, monkeypatch):
    from django.core.files.uploadedfile import SimpleUploadedFile
    from equipment.admin import UsageReportInlineForm

    settings.MEDIA_ROOT = str(tmp_path)
    equipment = Equipment.objects.create(group=group, code="PHOTO", name="合成设备")
    booking = Booking.objects.create(equipment=equipment, user=student_a,
        start_at=datetime(2026, 11, 1, 4, tzinfo=timezone.utc), end_at=datetime(2026, 11, 1, 5, tzinfo=timezone.utc))
    report = UsageReport.objects.create(
        booking=booking, condition="normal", photo="synthetic/old.jpg", photo_size=800,
    )
    now = datetime(2026, 12, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(storage.timezone, "now", lambda: now)
    monkeypatch.setattr(storage.shutil, "disk_usage", Mock(side_effect=OSError))
    assert "photo_size" not in UsageReportInlineForm.base_fields
    assert "photo_uploaded_at" not in UsageReportInlineForm.base_fields

    def amounts():
        group_row = next(g for g in storage.ops_summary()["groups"] if g["id"] == group.pk)
        return (group_row["modules"]["equipment"]["known_bytes"], group_row["months"]["2026-11"],
                group_row["months"]["2026-12"])

    assert amounts() == (800, 0, 0)  # historical known size, no proven month
    report.photo_uploaded_at = datetime(2026, 11, 30, 15, 59, tzinfo=timezone.utc)
    report.save(update_fields=["photo_uploaded_at"])
    previous_upload = report.photo_uploaded_at
    assert amounts() == (800, 800, 0)
    unchanged = UsageReportInlineForm(data={"condition": "normal", "photo_size": 1}, instance=report)
    assert unchanged.is_valid(), unchanged.errors
    unchanged.save()
    report.refresh_from_db()
    assert report.photo.name == "synthetic/old.jpg" and report.photo_size == 800
    assert report.photo_uploaded_at == previous_upload

    replacement = UsageReportInlineForm(data={"condition": "normal"},
        files={"photo": SimpleUploadedFile("new.jpg", b"test-image")}, instance=report)
    assert replacement.is_valid(), replacement.errors
    pending = replacement.save(commit=False)
    assert pending.photo_size == 10
    assert UsageReport.objects.get(pk=report.pk).photo_size == 800
    pending.save()
    report.refresh_from_db()
    assert report.photo.name.endswith(".jpg") and report.photo_size == 10
    assert report.photo_uploaded_at == now
    assert amounts() == (10, 0, 10)

    clear = UsageReportInlineForm(data={"condition": "normal", "photo-clear": "on"}, instance=report)
    assert clear.is_valid(), clear.errors
    clear.save()
    report.refresh_from_db()
    assert not report.photo and report.photo_size is None and report.photo_uploaded_at is None
    assert amounts() == (0, 0, 0)

def test_wrong_nas_volume_has_no_capacity(settings, tmp_path, monkeypatch):
    from core.nas_storage import MARKER, NasFileStorage

    settings.LAB_NAS_STORAGE_ID = "expected"
    files = tmp_path / "files"
    files.mkdir()
    (tmp_path / MARKER).write_bytes(b"other-volume\n")
    monkeypatch.setattr(storage, "default_storage", NasFileStorage(location=str(files)))
    assert storage.mount_info()["filesystem"] is None
