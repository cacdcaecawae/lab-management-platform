"""Dataset version codes (git style) pinned by submitted records. See datasets/versions.py."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

pytestmark = pytest.mark.django_db


def new_dataset(client, project, name, kind="raw"):
    return client.post("/api/datasets/", {"project_id": project.id, "name": name, "kind": kind}, format="json").json()


def upload(client, dataset_id, name, content=b"x"):
    r = client.post(f"/api/datasets/{dataset_id}/files/", {"file": SimpleUploadedFile(name, content)}, format="multipart")
    assert r.status_code == 201, r.content


def version_of(client, dataset_id):
    return client.get(f"/api/datasets/{dataset_id}/").json()["version"]


def submitted_experiment(client, project, dataset_id):
    body = {"project_id": project.id, "title": "t", "date": "2026-11-16", "dataset_ids": [dataset_id]}
    exp = client.post("/api/experiments/", body, format="json").json()
    assert exp["datasets"][0]["version"] is None  # a draft follows the latest files
    return client.post(f"/api/experiments/{exp['id']}/submit/").json()


def test_version_depends_on_the_files_not_on_upload_order(api, project, student_a):
    a = api(student_a)
    first, second = new_dataset(a, project, "first"), new_dataset(a, project, "second")
    for name in ("a.mat", "b.mat"):
        upload(a, first["id"], name, name.encode())
    for name in ("b.mat", "a.mat"):
        upload(a, second["id"], name, name.encode())
    v = version_of(a, first["id"])
    assert len(v) == 64 and v == version_of(a, second["id"])
    upload(a, first["id"], "c.mat")
    assert version_of(a, first["id"]) != v


def test_submit_pins_the_version_and_later_uploads_do_not_move_it(api, project, student_a):
    a = api(student_a)
    raw = new_dataset(a, project, "raw")
    upload(a, raw["id"], "01.mat")
    exp = submitted_experiment(a, project, raw["id"])
    pinned = exp["datasets"][0]["version"]
    assert pinned == version_of(a, raw["id"]) and exp["datasets"][0]["changed"] is False

    upload(a, raw["id"], "02.mat")  # datasets are not frozen any more
    cited = a.get(f"/api/experiments/{exp['id']}/").json()["datasets"][0]
    assert cited["version"] == pinned and cited["changed"] is True

    url = f"/api/datasets/{raw['id']}/files/"
    assert [f["name"] for f in a.get(url, {"version": pinned}).json()] == ["01.mat"]
    assert [f["name"] for f in a.get(url).json()] == ["01.mat", "02.mat"]


def test_return_clears_the_pin_and_resubmit_pins_the_new_version(api, project, student_a, advisor):
    a = api(student_a)
    raw = new_dataset(a, project, "raw")
    upload(a, raw["id"], "01.mat")
    exp = submitted_experiment(a, project, raw["id"])
    first = exp["datasets"][0]["version"]
    upload(a, raw["id"], "02.mat")

    returned = api(advisor).post(f"/api/experiments/{exp['id']}/return/", {"reason": "补数据"}, format="json").json()
    assert returned["datasets"][0]["version"] is None
    second = a.post(f"/api/experiments/{exp['id']}/submit/").json()["datasets"][0]["version"]
    assert second not in (None, first)

    url = f"/api/datasets/{raw['id']}/files/"
    assert len(a.get(url, {"version": first}).json()) == 1  # the old version can still be listed
    assert len(a.get(url, {"version": second}).json()) == 2


def test_runs_and_reports_pin_every_cited_dataset(api, project, student_a):
    a = api(student_a)
    raw, script, result = new_dataset(a, project, "raw"), new_dataset(a, project, "s", "script"), new_dataset(a, project, "r", "result")
    for dataset, name in ((raw, "01.mat"), (script, "run.m"), (result, "out.csv")):
        upload(a, dataset["id"], name)
    body = {"project_id": project.id, "title": "t", "input_ids": [raw["id"]], "script_dataset_id": script["id"],
            "environment": "MATLAB R2024b", "output_dataset_id": result["id"]}
    run = a.post("/api/runs/", body, format="json").json()
    run = a.post(f"/api/runs/{run['id']}/submit/").json()
    for cited in (run["inputs"][0], run["script_dataset"], run["output_dataset"]):
        assert cited["version"] == version_of(a, cited["id"])

    report = a.post("/api/reports/", {"week_start": "2026-11-16", "dataset_ids": [raw["id"]]}, format="json").json()
    report = a.post(f"/api/reports/{report['id']}/submit/").json()
    assert report["datasets"][0]["version"] == run["inputs"][0]["version"]


def test_versions_follow_the_dataset_permissions(api, project, student_a, student_b, manager, advisor, other_manager):
    a = api(student_a)
    raw = new_dataset(a, project, "raw")
    upload(a, raw["id"], "01.mat")
    pinned = submitted_experiment(a, project, raw["id"])["datasets"][0]["version"]
    url = f"/api/datasets/{raw['id']}/files/"
    assert a.get(url, {"version": "0" * 64}).status_code == 404
    for outsider in (manager, other_manager):
        assert api(outsider).get(url, {"version": pinned}).status_code == 404
    # the advisor, and student_b as a member of the project the submitted experiment names
    for reader in (advisor, student_b):
        assert api(reader).get(url, {"version": pinned}).status_code == 200
