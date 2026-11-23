import datetime
import io
import zipfile

import pytest

from datasets.models import Dataset
from reports.models import WeeklyReport
from research.models import Experiment, ProcessingRun

pytestmark = pytest.mark.django_db


def _drain(resp):
    return b"".join(resp.streaming_content) if resp.streaming else resp.content


def test_download_zip_streams_all_files(api, student_a, manager, advisor, dataset_a, upload):
    upload(api(student_a), dataset_a, [("a.csv", b"t,v\n1,2\n"), ("波形说明.txt", "中文内容".encode())])

    for user in (student_a, manager, advisor):
        resp = api(user).get(f"/api/datasets/{dataset_a.pk}/download-zip/")
        assert resp.status_code == 200
        assert resp["Content-Type"] == "application/zip"
        assert resp["Cache-Control"] == "private, no-store"
        assert f"{dataset_a.code}.zip" in resp["Content-Disposition"]
        raw = _drain(resp)
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            assert sorted(zf.namelist()) == ["a.csv", "波形说明.txt"]
            assert zf.read("a.csv") == b"t,v\n1,2\n"
            assert zf.read("波形说明.txt") == "中文内容".encode()


def test_download_zip_with_version_snapshot(api, student_a, project, dataset_a, upload):
    client = api(student_a)
    upload(client, dataset_a, [("v1.csv", b"one")])
    exp = Experiment.objects.create(owner=student_a, project=project, title="标定", date=datetime.date(2026, 11, 16))
    exp.datasets.add(dataset_a)
    submitted = client.post(f"/api/experiments/{exp.pk}/submit/").json()
    pinned = submitted["datasets"][0]["version"]

    upload(client, dataset_a, [("v2.csv", b"two")])

    resp = client.get(f"/api/datasets/{dataset_a.pk}/download-zip/", {"version": pinned})
    assert resp.status_code == 200
    with zipfile.ZipFile(io.BytesIO(_drain(resp))) as zf:
        assert zf.namelist() == ["v1.csv"]

    assert client.get(f"/api/datasets/{dataset_a.pk}/download-zip/", {"version": "0" * 64}).status_code == 404


def test_download_zip_empty_is_409(api, student_a, dataset_a):
    resp = api(student_a).get(f"/api/datasets/{dataset_a.pk}/download-zip/")
    assert resp.status_code == 409
    assert resp.json()["code"] == "empty_dataset"


def test_download_zip_too_large_is_413(api, student_a, dataset_a, upload, settings):
    settings.DATASET_ZIP_MAX_BYTES = 10
    upload(api(student_a), dataset_a, [("a.bin", b"123456"), ("b.bin", b"12345")])
    resp = api(student_a).get(f"/api/datasets/{dataset_a.pk}/download-zip/")
    assert resp.status_code == 413
    assert resp.json()["code"] == "too_large_for_zip"


def test_download_zip_missing_backing_file_is_404(api, student_a, dataset_a, upload, stored_files):
    upload(api(student_a), dataset_a, [("gone.csv", b"data")])
    for path in stored_files():
        path.unlink()
    resp = api(student_a).get(f"/api/datasets/{dataset_a.pk}/download-zip/")
    assert resp.status_code == 404


def test_download_zip_isolation(api, student_a, student_b, other_manager, dataset_b, upload):
    upload(api(student_b), dataset_b, [("secret.csv", b"123")])
    assert api(student_a).get(f"/api/datasets/{dataset_b.pk}/download-zip/").status_code == 404
    assert api(other_manager).get(f"/api/datasets/{dataset_b.pk}/download-zip/").status_code == 404


def test_references_lists_experiments_runs_and_reports(api, student_a, student_b, manager, other_manager, project, dataset_a):
    exp = Experiment.objects.create(owner=student_a, project=project, title="兰姆波实验", date=datetime.date(2026, 11, 16))
    exp.datasets.add(dataset_a)

    script_ds = Dataset.objects.create(owner=student_a, project=project, name="脚本集", kind="script")
    run_in = ProcessingRun.objects.create(owner=student_a, project=project, title="滤波处理", script_dataset=script_ds)
    run_in.inputs.add(dataset_a)
    run_out = ProcessingRun.objects.create(owner=student_a, project=project, title="同时读写", output_dataset=dataset_a)
    run_out.inputs.add(dataset_a)

    rep = WeeklyReport.objects.create(owner=student_a, week_start=datetime.date(2026, 11, 16), status="submitted")
    rep.datasets.add(dataset_a)

    for user in (student_a, manager):
        resp = api(user).get(f"/api/datasets/{dataset_a.pk}/references/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["experiments"] == [{"id": exp.id, "code": exp.code, "title": "兰姆波实验", "status": "draft"}]
        assert {r["id"]: r["roles"] for r in body["runs"]} == {
            run_in.id: ["input"],
            run_out.id: ["input", "output"],
        }
        assert body["reports"] == [{
            "id": rep.id,
            "week_start": "2026-11-16",
            "status": "submitted",
            "owner": {"id": student_a.id, "name": student_a.name},
        }]

    # Isolation
    assert api(student_b).get(f"/api/datasets/{dataset_a.pk}/references/").status_code == 404
    assert api(other_manager).get(f"/api/datasets/{dataset_a.pk}/references/").status_code == 404
