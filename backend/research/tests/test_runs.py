import pytest

from datasets.models import Dataset
from research.models import ProcessingRun

from .factories import make_dataset, make_run

pytestmark = pytest.mark.django_db

URL = "/api/runs/"
SCRIPT, RESULT = Dataset.Kind.SCRIPT, Dataset.Kind.RESULT


def test_create_run_with_script_dataset(api, student_a, project):
    raw = make_dataset(student_a, project)
    script = make_dataset(student_a, project, SCRIPT, "脚本")
    result = make_dataset(student_a, project, RESULT, "结果")
    response = api(student_a).post(
        URL,
        {
            "project_id": project.pk, "title": "包络提取", "input_ids": [raw.pk], "script_dataset_id": script.pk,
            "script_path": "main.py", "params": {"窗长": 128}, "environment": "Python 3.12",
            "output_dataset_id": result.pk,
        },
        format="json",
    )
    assert response.status_code == 201, response.json()
    data = response.json()
    assert data["code"] == f"RUN-2026-{data['id']:04d}"
    assert data["status"] == "draft"
    assert [d["id"] for d in data["inputs"]] == [raw.pk]
    assert data["script_dataset"] == {"id": script.pk, "code": script.code, "name": "脚本", "kind": "script", "version": None, "changed": False}
    assert data["output_dataset"]["id"] == result.pk

    response = api(student_a).post(f"{URL}{data['id']}/submit/")
    assert response.status_code == 200, response.json()


def test_dataset_kinds_are_checked(api, student_a, project):
    raw = make_dataset(student_a, project)
    response = api(student_a).post(
        URL,
        {"project_id": project.pk, "title": "t", "script_dataset_id": raw.pk, "output_dataset_id": raw.pk},
        format="json",
    )
    assert response.status_code == 400
    assert set(response.json()["errors"]) == {"script_dataset_id", "output_dataset_id"}


def test_datasets_must_belong_to_the_owner(api, student_a, student_b, project):
    run = make_run(student_a, project)
    fields = {
        "input_ids": [make_dataset(student_b, project).pk],
        "script_dataset_id": make_dataset(student_b, project, SCRIPT).pk,
        "output_dataset_id": make_dataset(student_b, project, RESULT).pk,
    }
    response = api(student_a).patch(f"{URL}{run.pk}/", fields, format="json")
    assert response.status_code == 400
    assert set(response.json()["errors"]) == set(fields)


def test_params_must_be_an_object(api, student_a, project):
    response = api(student_a).post(URL, {"project_id": project.pk, "title": "t", "params": [1]}, format="json")
    assert response.status_code == 400
    assert "params" in response.json()["errors"]


def test_script_dataset_can_be_cleared(api, student_a, project):
    run = make_run(student_a, project, script_dataset=make_dataset(student_a, project, SCRIPT))
    response = api(student_a).patch(f"{URL}{run.pk}/", {"script_dataset_id": None}, format="json")
    assert response.status_code == 200
    assert response.json()["script_dataset"] is None


def test_submit_lists_everything_missing(api, student_a, project):
    run = ProcessingRun.objects.create(owner=student_a, project=project, title="空记录")
    response = api(student_a).post(f"{URL}{run.pk}/submit/")
    assert response.status_code == 400
    assert set(response.json()["errors"]) == {"inputs", "script_dataset", "environment", "output_dataset"}
    run.refresh_from_db()
    assert run.status == "draft"


@pytest.mark.parametrize(
    "repo, commit, missing",
    [("https://git.example.com/x.git", "", "script_commit"), ("", "a1b2c3d", "script_repo")],
)
def test_submit_needs_both_repo_and_commit(api, student_a, project, repo, commit, missing):
    run = make_run(student_a, project, script_repo=repo, script_commit=commit)
    response = api(student_a).post(f"{URL}{run.pk}/submit/")
    assert response.status_code == 400
    assert list(response.json()["errors"]) == [missing]


def test_list_has_no_n_plus_1(api, student_a, project, django_assert_max_num_queries):
    for _ in range(5):
        make_run(student_a, project, script_dataset=make_dataset(student_a, project, SCRIPT))
    client = api(student_a)
    # session + user + count + page (with joined datasets) + inputs prefetch
    with django_assert_max_num_queries(5):
        assert client.get(URL).json()["count"] == 5
