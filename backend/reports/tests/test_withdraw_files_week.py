"""Issue #58 P4-2: take a report back before it is reviewed, images and files on a report, this week's records."""
from datetime import date, datetime
from pathlib import Path

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from datasets.models import Dataset
from reports.models import ReportFeedback, ReportFile, WeeklyReport
from research.models import Experiment, ProcessingRun

pytestmark = pytest.mark.django_db

URL = "/api/reports/"
MONDAY = date(2026, 11, 16)
S = WeeklyReport.Status


def stored_files():
    return [p for p in Path(settings.MEDIA_ROOT).rglob("*") if p.is_file()]


def test_withdraw_before_review(api, project, student_a, student_b, advisor, other_advisor):
    data = Dataset.objects.create(owner=student_a, project=project, name="波形")
    report = WeeklyReport.objects.create(owner=student_a, week_start=MONDAY)
    report.datasets.add(data)
    student = api(student_a)
    assert student.post(f"{URL}{report.pk}/withdraw/").status_code == 409  # a draft
    assert student.post(f"{URL}{report.pk}/submit/").status_code == 200
    assert WeeklyReport.objects.get().data_versions

    assert api(student_b).post(f"{URL}{report.pk}/withdraw/").status_code == 404
    assert api(other_advisor).post(f"{URL}{report.pk}/withdraw/").status_code == 404
    assert api(advisor).post(f"{URL}{report.pk}/withdraw/").status_code == 403  # not the owner
    r = student.post(f"{URL}{report.pk}/withdraw/")
    assert r.status_code == 200 and r.data["status"] == "draft" and r.data["submitted_at"] is None
    assert WeeklyReport.objects.get().data_versions == {}  # the next submit pins again
    assert student.patch(f"{URL}{report.pk}/", {"done": "补上第 3 组"}, format="json").status_code == 200

    assert student.post(f"{URL}{report.pk}/submit/").status_code == 200
    assert api(advisor).post(f"{URL}{report.pk}/feedback/", {"verdict": "reviewed"}, format="json").status_code == 200
    refused = student.post(f"{URL}{report.pk}/withdraw/")
    assert refused.status_code == 409 and refused.data["code"] == "invalid_state"


def test_withdrawing_a_resubmission_goes_back_to_needs_revision(api, student_a, advisor):
    report = WeeklyReport.objects.create(owner=student_a, week_start=MONDAY, status=S.SUBMITTED, submitted_at=timezone.now())
    student = api(student_a)
    sent_back = api(advisor).post(f"{URL}{report.pk}/feedback/", {"verdict": "needs_revision", "content": "补数据"}, format="json")
    assert sent_back.status_code == 200
    assert student.post(f"{URL}{report.pk}/submit/").status_code == 200

    r = student.post(f"{URL}{report.pk}/withdraw/")
    assert r.status_code == 200 and r.data["status"] == "needs_revision" and r.data["submitted_at"]
    assert len(r.data["feedback"]) == 1
    assert student.delete(f"{URL}{report.pk}/").status_code == 409  # only drafts: the feedback stays
    assert ReportFeedback.objects.count() == 1


def test_report_files(api, django_capture_on_commit_callbacks, student_a, student_b, advisor, other_advisor):
    report = WeeklyReport.objects.create(owner=student_a, week_start=MONDAY)
    student = api(student_a)
    upload = f"{URL}{report.pk}/files/"
    r = student.post(upload, {"file": SimpleUploadedFile("包络对比.png", b"\x89PNG")})
    assert r.status_code == 201 and r.data["name"] == "包络对比.png"
    assert api(advisor).post(upload, {"file": SimpleUploadedFile("x.png", b"x")}).status_code == 403
    assert api(student_b).post(upload, {"file": SimpleUploadedFile("x.png", b"x")}).status_code == 404
    assert api(other_advisor).post(upload, {"file": SimpleUploadedFile("x.png", b"x")}).status_code == 404

    image = api(advisor).get(r.data["url"])
    assert image.status_code == 200 and b"".join(image.streaming_content) == b"\x89PNG"
    assert api(student_b).get(r.data["url"]).status_code == 404
    assert api(other_advisor).get(r.data["url"]).status_code == 404
    assert [f["name"] for f in student.get(f"{URL}{report.pk}/").data["files"]] == ["包络对比.png"]

    assert student.post(f"{URL}{report.pk}/submit/").status_code == 200
    digest = api(advisor).get(f"{URL}digest/", {"week_start": "2026-11-16"}).data["reports"]
    assert [f["name"] for f in digest[0]["files"]] == ["包络对比.png"]
    late = student.post(upload, {"file": SimpleUploadedFile("晚了.png", b"x")})
    assert late.status_code == 409 and ReportFile.objects.count() == 1 and len(stored_files()) == 1
    file_url = f"/api/report-files/{r.data['id']}/"
    assert student.delete(file_url).status_code == 409
    assert api(advisor).delete(file_url).status_code == 403
    assert api(student_b).delete(file_url).status_code == 404

    assert student.post(f"{URL}{report.pk}/withdraw/").status_code == 200
    with django_capture_on_commit_callbacks(execute=True):
        assert student.delete(file_url).status_code == 204
    assert not ReportFile.objects.exists() and not stored_files()


def test_deleting_a_draft_removes_its_files(api, django_capture_on_commit_callbacks, student_a):
    report = WeeklyReport.objects.create(owner=student_a, week_start=MONDAY)
    student = api(student_a)
    assert student.post(f"{URL}{report.pk}/files/", {"file": SimpleUploadedFile("a.jpg", b"jpg")}).status_code == 201
    with django_capture_on_commit_callbacks(execute=True):
        assert student.delete(f"{URL}{report.pk}/").status_code == 204
    assert not stored_files()


def test_week_records_are_the_owners_records_created_or_submitted_that_week(api, project, student_a, student_b):
    def at(*day_and_time):
        return timezone.make_aware(datetime(*day_and_time))  # Asia/Shanghai, the server's time zone

    def experiment(owner, title, created, submitted=None):
        e = Experiment.objects.create(owner=owner, project=project, title=title, date=MONDAY, submitted_at=submitted)
        Experiment.objects.filter(pk=e.pk).update(created_at=created)
        return e

    def run(owner, title, created):
        r = ProcessingRun.objects.create(owner=owner, project=project, title=title)
        ProcessingRun.objects.filter(pk=r.pk).update(created_at=created)
        return r

    new = experiment(student_a, "本周新建", at(2026, 11, 18, 10))
    submitted = experiment(student_a, "上周建、本周提交", at(2026, 11, 10, 9), submitted=at(2026, 11, 16, 0, 30))
    experiment(student_a, "上周的", at(2026, 11, 10, 9), submitted=at(2026, 11, 15, 23, 59))
    experiment(student_b, "别人的", at(2026, 11, 18, 10))
    sunday = run(student_a, "周日夜里", at(2026, 11, 22, 23, 30))
    run(student_a, "下周一", at(2026, 11, 23, 0, 10))

    r = api(student_a).get(f"{URL}week-records/", {"week_start": "2026-11-16"})
    assert r.status_code == 200
    assert [e["id"] for e in r.data["experiments"]] == [submitted.id, new.id]
    assert [x["id"] for x in r.data["runs"]] == [sunday.id]
    assert set(r.data["experiments"][0]) == {"id", "code", "title", "status"}
    assert api(student_b).get(f"{URL}week-records/", {"week_start": "2026-11-16"}).data["runs"] == []
    assert api(student_a).get(f"{URL}week-records/", {"week_start": "2026-11-18"}).status_code == 400
