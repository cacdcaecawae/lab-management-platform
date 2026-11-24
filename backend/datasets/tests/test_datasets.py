import datetime
import hashlib

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from datasets.models import Dataset
from projects.models import Project
from reports.models import WeeklyReport
from research.models import Experiment, ProcessingRun

pytestmark = pytest.mark.django_db


def test_create_sets_owner_and_returns_contract_shape(api, student_a, project):
    resp = api(student_a).post(
        "/api/datasets/", {"project_id": project.pk, "name": "第一批", "kind": "raw", "description": "d"}, format="json"
    )
    assert resp.status_code == 201
    body = resp.json()
    ds = Dataset.objects.get()
    assert ds.owner == student_a
    assert body == {
        "id": ds.pk, "code": ds.code, "project": {"id": project.pk, "name": project.name},
        "owner": {"id": student_a.pk, "name": student_a.name}, "name": "第一批", "kind": "raw", "description": "d",
        "file_count": 0, "total_size": 0, "version": hashlib.sha256(b"").hexdigest(),  # empty dataset
        "created_at": body["created_at"], "updated_at": body["updated_at"],
    }


def test_create_rejects_project_of_other_group(api, student_a, other_group, other_manager):
    foreign = Project.objects.create(group=other_group, name="外组项目", leader=other_manager)
    resp = api(student_a).post("/api/datasets/", {"project_id": foreign.pk, "name": "x"}, format="json")
    assert resp.status_code == 400
    assert "project_id" in resp.json()["errors"]
    assert not Dataset.objects.exists()


def test_list_counts_files_and_sizes(api, student_a, dataset_a, upload):
    client = api(student_a)
    upload(client, dataset_a, [("a.bin", b"12345"), ("b.bin", b"123")])
    Dataset.objects.create(owner=student_a, project=dataset_a.project, name="空")
    results = {d["name"]: d for d in client.get("/api/datasets/").json()["results"]}
    assert (results[dataset_a.name]["file_count"], results[dataset_a.name]["total_size"]) == (2, 8)
    assert (results["空"]["file_count"], results["空"]["total_size"]) == (0, 0)


def test_list_query_count_does_not_grow_with_rows(api, student_a, project, upload):
    client = api(student_a)

    def list_queries():
        with CaptureQueriesContext(connection) as ctx:
            assert client.get("/api/datasets/").status_code == 200
        return len(ctx)

    ds = Dataset.objects.create(owner=student_a, project=project, name="1")
    upload(client, ds, [("a", b"a")])
    one = list_queries()
    for i in range(3):
        upload(client, Dataset.objects.create(owner=student_a, project=project, name=f"n{i}"), [("a", b"a")])
    assert list_queries() == one


def test_list_scope(api, student_a, manager, advisor, other_manager, dataset_a, dataset_b):
    def names(user):
        return {d["name"] for d in api(user).get("/api/datasets/").json()["results"]}

    assert names(student_a) == {dataset_a.name}
    assert names(advisor) == {dataset_a.name, dataset_b.name}
    assert names(manager) == set()  # a student with the 管理员 tag: their own datasets only
    assert names(other_manager) == set()


def test_list_filters(api, advisor, student_a, student_b, project, group):
    other_project = Project.objects.create(group=group, name="另一个项目", leader=student_a)
    Dataset.objects.create(owner=student_a, project=project, name="兰姆波 原始", kind="raw")
    Dataset.objects.create(owner=student_a, project=other_project, name="处理脚本", kind="script")
    Dataset.objects.create(owner=student_b, project=project, name="兰姆波 结果", kind="result")
    client = api(advisor)

    def names(query):
        resp = client.get(f"/api/datasets/?{query}")
        assert resp.status_code == 200
        return {d["name"] for d in resp.json()["results"]}

    assert names(f"project={other_project.pk}") == {"处理脚本"}
    assert names("kind=result") == {"兰姆波 结果"}
    assert names(f"owner={student_a.pk}") == {"兰姆波 原始", "处理脚本"}
    assert names("search=兰姆波") == {"兰姆波 原始", "兰姆波 结果"}
    assert names(f"owner={student_a.pk}&kind=raw") == {"兰姆波 原始"}
    assert client.get("/api/datasets/?project=abc").status_code == 400


def test_patch_only_changes_name_and_description(api, student_a, dataset_a, project, group, upload):
    upload(api(student_a), dataset_a, [("a.bin", b"1234")])
    other_project = Project.objects.create(group=group, name="另一个项目", leader=student_a)
    resp = api(student_a).patch(
        f"/api/datasets/{dataset_a.pk}/",
        {"name": "新名字", "description": "新说明", "project_id": other_project.pk, "kind": "script"},
        format="json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert (body["name"], body["description"]) == ("新名字", "新说明")
    assert (body["project"]["id"], body["kind"]) == (project.pk, "raw")
    assert (body["file_count"], body["total_size"]) == (1, 4)
    dataset_a.refresh_from_db()
    assert (dataset_a.project_id, dataset_a.kind, dataset_a.name) == (project.pk, "raw", "新名字")


def test_put_is_not_allowed(api, student_a, dataset_a):
    resp = api(student_a).put(f"/api/datasets/{dataset_a.pk}/", {"name": "x"}, format="json")
    assert resp.status_code == 405


def test_advisor_can_read_but_not_write(api, manager, advisor, dataset_a):
    client = api(advisor)
    assert client.get(f"/api/datasets/{dataset_a.pk}/").status_code == 200
    assert client.patch(f"/api/datasets/{dataset_a.pk}/", {"name": "x"}, format="json").status_code == 403
    assert client.delete(f"/api/datasets/{dataset_a.pk}/").status_code == 403
    assert api(manager).get(f"/api/datasets/{dataset_a.pk}/").status_code == 404
    dataset_a.refresh_from_db()
    assert dataset_a.name == "A 原始波形"


def test_out_of_scope_dataset_is_404(api, student_a, other_manager, dataset_b):
    for user in (student_a, other_manager):
        client = api(user)
        url = f"/api/datasets/{dataset_b.pk}/"
        assert client.get(url).status_code == 404
        assert client.patch(url, {"name": "x"}, format="json").status_code == 404
        assert client.delete(url).status_code == 404
    assert Dataset.objects.filter(pk=dataset_b.pk, name="B 原始波形").exists()


def test_delete_empty_unreferenced_dataset(api, student_a, dataset_a):
    assert api(student_a).delete(f"/api/datasets/{dataset_a.pk}/").status_code == 204
    assert not Dataset.objects.filter(pk=dataset_a.pk).exists()


def test_delete_dataset_with_files_is_409(api, student_a, dataset_a, upload):
    upload(api(student_a), dataset_a, [("a.bin", b"1")])
    resp = api(student_a).delete(f"/api/datasets/{dataset_a.pk}/")
    assert resp.status_code == 409
    assert resp.json()["code"] == "invalid_state"
    assert Dataset.objects.filter(pk=dataset_a.pk).exists()


def _reference_by_experiment(ds):
    Experiment.objects.create(owner=ds.owner, project=ds.project, title="t", date=datetime.date(2026, 11, 16)).datasets.add(ds)


def _reference_as_run_input(ds):
    ProcessingRun.objects.create(owner=ds.owner, project=ds.project, title="t").inputs.add(ds)


def _reference_as_run_script(ds):
    ProcessingRun.objects.create(owner=ds.owner, project=ds.project, title="t", script_dataset=ds)


def _reference_as_run_output(ds):
    ProcessingRun.objects.create(owner=ds.owner, project=ds.project, title="t", output_dataset=ds)


def _reference_by_report(ds):
    WeeklyReport.objects.create(owner=ds.owner, week_start=datetime.date(2026, 11, 16)).datasets.add(ds)


@pytest.mark.parametrize(
    "reference",
    [_reference_by_experiment, _reference_as_run_input, _reference_as_run_script, _reference_as_run_output, _reference_by_report],
)
def test_delete_referenced_dataset_is_409(api, student_a, dataset_a, reference):
    reference(dataset_a)
    resp = api(student_a).delete(f"/api/datasets/{dataset_a.pk}/")
    assert resp.status_code == 409
    assert resp.json()["code"] == "invalid_state"
    assert Dataset.objects.filter(pk=dataset_a.pk).exists()
