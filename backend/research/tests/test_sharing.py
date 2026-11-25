"""P1-3: a submitted experiment or processing run of a project is read by the project's current members (the leader
included): the record, its files and photos. Drafts and records without a project stay with the owner and the
group's advisors; nobody but the owner writes."""

import datetime

import pytest
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile

from conftest import make_user
from projects.models import Project
from reports.models import WeeklyReport
from research.models import Experiment, ExperimentPhoto, RecordStatus

from .factories import add_file, make_experiment, make_run

pytestmark = pytest.mark.django_db


@pytest.fixture(params=["experiments", "runs"])
def resource(request):
    return request.param


def submitted(record):
    type(record).objects.filter(pk=record.pk).update(status=RecordStatus.SUBMITTED)
    return record


@pytest.fixture
def shared(resource, student_a, project):
    """student_a's submitted record of `project` (members student_a, student_b)."""
    return submitted((make_experiment if resource == "experiments" else make_run)(student_a, project))


def own_files(record):
    return record.dataset if isinstance(record, Experiment) else record.output_dataset


def test_project_members_read_a_submitted_record_and_its_files(api, resource, shared, student_b):
    data_file = add_file(own_files(shared))
    client = api(student_b)
    assert client.get(f"/api/{resource}/{shared.pk}/").status_code == 200
    assert client.get(f"/api/{resource}/{shared.pk}/history/").status_code == 200
    assert [r["id"] for r in client.get(f"/api/{resource}/").json()["results"]] == [shared.pk]
    assert [r["id"] for r in client.get(f"/api/{resource}/", {"owner": shared.owner_id}).json()["results"]] == [shared.pk]
    dataset = own_files(shared)
    assert client.get(f"/api/datasets/{dataset.pk}/").status_code == 200
    assert [f["id"] for f in client.get(f"/api/datasets/{dataset.pk}/files/").json()] == [data_file.pk]
    assert client.get(f"/api/files/{data_file.pk}/download/").status_code == 200
    assert client.get(f"/api/datasets/{dataset.pk}/download-zip/").status_code == 200


def test_project_members_do_not_write_it(api, resource, shared, student_b):
    client = api(student_b)
    url = f"/api/{resource}/{shared.pk}/"
    assert client.patch(url, {"title": "x"}, format="json").status_code == 403
    assert client.delete(url).status_code == 403
    assert client.post(f"{url}submit/").status_code == 403
    assert client.post(f"{url}return/", {"reason": "x"}, format="json").status_code == 403
    dataset = own_files(shared)
    data_file = add_file(dataset)
    response = client.post(f"/api/datasets/{dataset.pk}/files/", {"file": SimpleUploadedFile("x.csv", b"x")}, format="multipart")
    assert response.status_code == 403
    assert client.delete(f"/api/files/{data_file.pk}/").status_code == 403


def test_drafts_and_records_without_a_project_are_not_shared(api, resource, student_a, student_b, project):
    make = make_experiment if resource == "experiments" else make_run
    draft = make(student_a, project)
    no_project = submitted(make(student_a, None))
    client = api(student_b)
    for record in (draft, no_project):
        assert client.get(f"/api/{resource}/{record.pk}/").status_code == 404
        assert client.get(f"/api/datasets/{own_files(record).pk}/").status_code == 404
    assert client.get(f"/api/{resource}/").json()["count"] == 0


def test_only_current_members_and_the_leader_read(api, resource, shared, group, student_a, student_b, manager, other_advisor, project):
    # the group's 管理员 who is not in the project, and another group's advisor: as before, nothing
    for outsider in (manager, other_advisor):
        assert api(outsider).get(f"/api/{resource}/{shared.pk}/").status_code == 404
    # a member who leaves the project loses it
    project.members.remove(student_b)
    assert api(student_b).get(f"/api/{resource}/{shared.pk}/").status_code == 404
    # a leader is a member even if left out of the member list
    leader = make_user("leader", group)
    Project.objects.filter(pk=project.pk).update(leader=leader)
    assert api(leader).get(f"/api/{resource}/{shared.pk}/").status_code == 200


def test_a_returned_record_is_private_again(api, resource, shared, student_b, advisor):
    assert api(advisor).post(f"/api/{resource}/{shared.pk}/return/", {"reason": "补参数"}, format="json").status_code == 200
    assert api(student_b).get(f"/api/{resource}/{shared.pk}/").status_code == 404


def test_project_members_see_the_photos_of_a_shared_experiment(api, student_a, student_b, project):
    experiment = make_experiment(student_a, project)
    photo = ExperimentPhoto(experiment=experiment, name="现场.jpg", size=3, uploaded_by=student_a)
    photo.file.save("现场.jpg", ContentFile(b"jpg"), save=True)
    url = f"/api/experiment-photos/{photo.pk}/file/"
    assert api(student_b).get(url).status_code == 404
    submitted(experiment)
    assert api(student_b).get(url).status_code == 200
    assert api(student_b).delete(f"/api/experiment-photos/{photo.pk}/").status_code == 403


def test_teammates_cite_a_shared_experiment_in_their_own_run(api, student_a, student_b, project, advisor):
    theirs = submitted(make_experiment(student_a, project))
    draft = make_experiment(student_a, project, title="草稿")
    client = api(student_b)
    response = client.post("/api/runs/", {"title": "复现", "experiment_ids": [draft.pk]}, format="json")
    assert response.status_code == 400 and "experiment_ids" in response.json()["errors"]
    response = client.post("/api/runs/", {"title": "复现", "experiment_ids": [theirs.pk], "method": "x", "conclusion": "y"}, format="json")
    assert response.status_code == 201, response.json()
    run_id = response.json()["id"]
    # returned to draft before the run is submitted: the draft still saves (the page saves before submitting) ...
    api(advisor).post(f"/api/experiments/{theirs.pk}/return/", {"reason": "补参数"}, format="json")
    assert client.patch(f"/api/runs/{run_id}/", {"experiment_ids": [theirs.pk]}, format="json").status_code == 200
    # ... but may not pin a record its owner can no longer see, nor take on another one
    response = client.post(f"/api/runs/{run_id}/submit/")
    assert response.status_code == 400
    assert theirs.code in response.json()["errors"]["experiments"][0]
    response = client.patch(f"/api/runs/{run_id}/", {"experiment_ids": [theirs.pk, draft.pk]}, format="json")
    assert response.status_code == 400 and "experiment_ids" in response.json()["errors"]


def test_references_list_runs_and_reports_citing_the_experiment(api, student_a, student_b, project, advisor):
    experiment = submitted(make_experiment(student_a, project))
    mine = make_run(student_a, project)
    mine.experiments.add(experiment)
    teammate = submitted(make_run(student_b, project))
    teammate.experiments.add(experiment)
    report = WeeklyReport.objects.create(owner=student_a, week_start=datetime.date(2026, 11, 16))
    report.experiments.add(experiment)
    url = f"/api/datasets/{experiment.dataset_id}/references/"

    refs = api(advisor).get(url).json()
    assert [e["id"] for e in refs["experiments"]] == [experiment.pk]  # the record holding these files
    assert {r["id"]: r["roles"] for r in refs["runs"]} == {mine.pk: ["input"], teammate.pk: ["input"]}
    assert [r["id"] for r in refs["reports"]] == [report.pk]
    # student_b sees the shared run but not student_a's draft run or weekly report
    refs = api(student_b).get(url).json()
    assert [r["id"] for r in refs["runs"]] == [teammate.pk] and refs["reports"] == []
