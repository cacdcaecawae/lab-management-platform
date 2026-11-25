"""P1-1 / P1-2: a record's own files and photos. The owner deletes a mistaken upload until a submitted record pins it,
and an unused draft goes away with its files; photos are added and removed while the record is a draft."""

import datetime
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from datasets.models import DataFile, Dataset, DatasetSnapshot
from equipment.models import Equipment
from projects.models import Project
from reports.models import WeeklyReport
from research.models import Experiment, ExperimentPhoto, ProcessingRun
from specimens.models import Specimen

from .factories import add_file, make_experiment, make_run

pytestmark = pytest.mark.django_db


def submit(client, resource, record):
    response = client.post(f"/api/{resource}/{record.pk}/submit/")
    assert response.status_code == 200, response.json()


def upload(client, dataset, name, content=b"t,amp\n0,1\n", **form):
    data = {"file": SimpleUploadedFile(name, content), **form}
    return client.post(f"/api/datasets/{dataset.pk}/files/", data, format="multipart")


@pytest.fixture
def stored_paths(settings):
    """Every file in the per-test storage directory."""
    root = Path(settings.MEDIA_ROOT)
    return lambda: sorted(p for p in root.rglob("*") if p.is_file()) if root.exists() else []


@pytest.fixture
def on_commit(django_capture_on_commit_callbacks):
    """Run the stored-file deletions that wait for the commit."""
    return lambda: django_capture_on_commit_callbacks(execute=True)


# --- the API creates a record with its own files ----------------------------------------------------------------


def test_a_new_experiment_comes_with_its_own_raw_data(api, student_a, project):
    response = api(student_a).post("/api/experiments/", {"title": "预紧力", "date": "2026-11-25"}, format="json")
    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["project"] is None  # 项目 is optional now
    experiment = Experiment.objects.get(pk=body["id"])
    assert (experiment.dataset.owner, experiment.dataset.kind, experiment.dataset.name) == (student_a, "raw", "预紧力")
    assert body["dataset"]["id"] == experiment.dataset_id and body["file_count"] == 0 and body["photos"] == []
    submit(api(student_a), "experiments", experiment)  # title and date are all a submit needs


def test_correcting_the_project_moves_the_records_files_along(api, student_a, project, group):
    other = Project.objects.create(group=group, name="另一个项目", leader=student_a)
    experiment, run = make_experiment(student_a, project), make_run(student_a, project)
    client = api(student_a)
    assert client.patch(f"/api/experiments/{experiment.pk}/", {"project_id": other.pk}, format="json").status_code == 200
    assert client.patch(f"/api/runs/{run.pk}/", {"project_id": None}, format="json").status_code == 200
    assert Dataset.objects.get(pk=experiment.dataset_id).project == other
    assert {d.project for d in Dataset.objects.filter(pk__in=[run.script_dataset_id, run.output_dataset_id])} == {None}


def test_list_filters_by_device_and_specimen(api, student_a, project, group, advisor):
    device = Equipment.objects.create(group=group, code="UT-001", name="超声探伤仪")
    specimen = Specimen.objects.create(group=group, code="SP-01", name="标准试块")
    on_device = make_experiment(student_a, project, equipment_item=device)
    on_specimen = make_experiment(student_a, project)
    on_specimen.specimen_items.add(specimen)
    client = api(advisor)

    def ids(**params):
        return [r["id"] for r in client.get("/api/experiments/", params).json()["results"]]

    assert ids(equipment_item=device.pk) == [on_device.pk]
    assert ids(specimen=specimen.pk) == [on_specimen.pk]
    assert client.get("/api/experiments/", {"specimen": "x"}).status_code == 400


# --- deleting a file --------------------------------------------------------------------------------------------


def test_owner_deletes_a_mistaken_upload(api, student_a, project, on_commit):
    experiment = make_experiment(student_a, project)
    client = api(student_a)
    [meta] = upload(client, experiment.dataset, "误传.csv").json()
    stored = Path(DataFile.objects.get(pk=meta["id"]).file.path)
    assert stored.exists()
    with on_commit():
        assert client.delete(f"/api/files/{meta['id']}/").status_code == 204
    assert not DataFile.objects.filter(pk=meta["id"]).exists()
    assert not stored.exists()


def test_a_file_a_submitted_record_pins_is_locked_until_the_record_is_returned(api, student_a, project, advisor):
    experiment = make_experiment(student_a, project)
    client = api(student_a)
    [meta] = upload(client, experiment.dataset, "01.csv").json()
    submit(client, "experiments", experiment)
    assert client.get(f"/api/datasets/{experiment.dataset_id}/files/").json()[0]["locked"] is True
    response = client.delete(f"/api/files/{meta['id']}/")
    assert response.status_code == 409 and response.json()["code"] == "invalid_state"

    # appended after the submit: not in the pinned version, so it can still go
    [later] = upload(client, experiment.dataset, "02.csv").json()
    assert later["locked"] is False
    assert client.delete(f"/api/files/{later['id']}/").status_code == 204

    api(advisor).post(f"/api/experiments/{experiment.pk}/return/", {"reason": "删掉误传的"}, format="json")
    assert client.delete(f"/api/files/{meta['id']}/").status_code == 204
    # the snapshot that held it is gone too: a later pin of the same version code must not find a file list with a gap
    assert not DatasetSnapshot.objects.filter(dataset=experiment.dataset).exists()


def test_a_submitted_weekly_report_pinning_a_dataset_locks_it(api, student_a, project):
    experiment = make_experiment(student_a, project)
    data_file = add_file(experiment.dataset)
    report = WeeklyReport.objects.create(owner=student_a, week_start=datetime.date(2026, 11, 16))
    report.datasets.add(experiment.dataset)
    assert api(student_a).post(f"/api/reports/{report.pk}/submit/").status_code == 200
    assert api(student_a).delete(f"/api/files/{data_file.pk}/").status_code == 409


def test_only_the_owner_deletes_files(api, student_a, student_b, advisor, project):
    data_file = add_file(make_experiment(student_a, project).dataset)
    assert api(advisor).delete(f"/api/files/{data_file.pk}/").status_code == 403  # sees it, does not own it
    assert api(student_b).delete(f"/api/files/{data_file.pk}/").status_code == 404  # a draft: not shared
    assert DataFile.objects.filter(pk=data_file.pk).exists()


# --- deleting a record ------------------------------------------------------------------------------------------


def test_an_unused_draft_goes_with_its_files_and_photos(api, student_a, project, on_commit, stored_paths):
    experiment = make_experiment(student_a, project)
    client = api(student_a)
    upload(client, experiment.dataset, "波形.csv")
    photo = client.post(f"/api/experiments/{experiment.pk}/photos/", {"file": SimpleUploadedFile("现场.jpg", b"jpg")}, format="multipart")
    assert photo.status_code == 201, photo.json()
    assert len(stored_paths()) == 2
    with on_commit():
        assert client.delete(f"/api/experiments/{experiment.pk}/").status_code == 204
    assert not Dataset.objects.filter(pk=experiment.dataset_id).exists()
    assert not ExperimentPhoto.objects.exists() and not DataFile.objects.exists()
    assert stored_paths() == []


@pytest.mark.parametrize("cited_by", ["run", "report", "another experiment"])
def test_a_cited_draft_is_not_deleted(api, student_a, project, cited_by):
    experiment = make_experiment(student_a, project)
    if cited_by == "run":
        make_run(student_a, project).experiments.add(experiment)
    elif cited_by == "report":
        WeeklyReport.objects.create(owner=student_a, week_start=datetime.date(2026, 11, 16)).datasets.add(experiment.dataset)
    else:
        make_experiment(student_a, project).datasets.add(experiment.dataset)
    response = api(student_a).delete(f"/api/experiments/{experiment.pk}/")
    assert response.status_code == 409 and response.json()["code"] == "invalid_state"
    assert Experiment.objects.filter(pk=experiment.pk).exists()


def test_a_deleted_run_keeps_scripts_its_copy_still_uses(api, student_a, project):
    source = make_run(student_a, project)
    response = api(student_a).post("/api/runs/", {"title": "复制", "script_dataset_id": source.script_dataset_id}, format="json")
    copy = ProcessingRun.objects.get(pk=response.json()["id"])
    assert api(student_a).delete(f"/api/runs/{source.pk}/").status_code == 204
    assert Dataset.objects.filter(pk=source.script_dataset_id).exists()  # shared with the copy
    assert not Dataset.objects.filter(pk=source.output_dataset_id).exists()
    assert api(student_a).delete(f"/api/runs/{copy.pk}/").status_code == 204
    assert not Dataset.objects.filter(pk__in=[source.script_dataset_id, copy.output_dataset_id]).exists()


# --- photos -----------------------------------------------------------------------------------------------------


def test_photos_are_added_and_removed_while_the_record_is_a_draft(api, student_a, student_b, advisor, project):
    experiment = make_experiment(student_a, project)
    client = api(student_a)
    url = f"/api/experiments/{experiment.pk}/photos/"
    response = client.post(url, {"file": SimpleUploadedFile("现场.png", b"png")}, format="multipart")
    assert response.status_code == 201
    photo = response.json()
    assert photo["name"] == "现场.png" and photo["url"] == f"/api/experiment-photos/{photo['id']}/file/"
    assert client.get(f"/api/experiments/{experiment.pk}/").json()["photos"] == [photo]
    opened = client.get(photo["url"])
    assert opened.status_code == 200 and "sandbox" in opened["Content-Security-Policy"]  # shows, never runs

    assert client.post(url, {"file": SimpleUploadedFile("说明.html", b"<p>")}, format="multipart").status_code == 400
    assert api(advisor).post(url, {"file": SimpleUploadedFile("a.png", b"x")}, format="multipart").status_code == 403
    assert api(student_b).post(url, {"file": SimpleUploadedFile("a.png", b"x")}, format="multipart").status_code == 404
    assert api(advisor).delete(f"/api/experiment-photos/{photo['id']}/").status_code == 403

    submit(client, "experiments", experiment)
    assert client.post(url, {"file": SimpleUploadedFile("b.png", b"x")}, format="multipart").status_code == 409
    assert client.delete(f"/api/experiment-photos/{photo['id']}/").status_code == 409
    api(advisor).post(f"/api/experiments/{experiment.pk}/return/", {"reason": "换张照片"}, format="json")
    assert client.delete(f"/api/experiment-photos/{photo['id']}/").status_code == 204


def test_other_groups_never_see_photos(api, student_a, project, other_advisor):
    experiment = make_experiment(student_a, project)
    response = api(student_a).post(
        f"/api/experiments/{experiment.pk}/photos/", {"file": SimpleUploadedFile("a.jpg", b"x")}, format="multipart"
    )
    assert api(other_advisor).get(response.json()["url"]).status_code == 404
