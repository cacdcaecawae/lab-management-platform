import pytest

from datasets.models import Dataset
from research.models import ProcessingRun

from .factories import add_file, make_dataset, make_experiment, make_run

pytestmark = pytest.mark.django_db

URL = "/api/runs/"
SCRIPT, RESULT = Dataset.Kind.SCRIPT, Dataset.Kind.RESULT


def test_create_run_cites_experiments_and_gets_its_own_files(api, student_a, project):
    experiment = make_experiment(student_a, project)
    response = api(student_a).post(
        URL,
        {
            "project_id": project.pk, "title": "包络提取", "experiment_ids": [experiment.pk],
            "method": "Origin 2024：5 点平滑后取峰值", "params": {"窗长": 128},
        },
        format="json",
    )
    assert response.status_code == 201, response.json()
    data = response.json()
    assert data["code"] == f"RUN-2026-{data['id']:04d}"
    assert data["status"] == "draft"
    assert data["experiments"] == [{
        "id": experiment.pk, "code": experiment.code, "title": experiment.title, "status": "draft",
        "owner": {"id": student_a.pk, "name": student_a.name}, "dataset_id": experiment.dataset_id,
        "version": None, "changed": False,
    }]
    run = ProcessingRun.objects.get(pk=data["id"])
    # scripts and results are uploaded on the run's page into datasets the run was created with
    assert (run.script_dataset.kind, run.script_dataset.owner, run.script_dataset.project) == (SCRIPT, student_a, project)
    assert (run.output_dataset.kind, run.output_dataset.name) == (RESULT, "包络提取 · 结果")
    assert data["script_dataset"]["id"] == run.script_dataset_id and data["output_dataset"]["id"] == run.output_dataset_id

    add_file(run.output_dataset, "对比曲线.png", b"png")
    response = api(student_a).post(f"{URL}{data['id']}/submit/")
    assert response.status_code == 200, response.json()
    pinned = response.json()["experiments"][0]["version"]
    assert pinned and ProcessingRun.objects.get(pk=run.pk).data_versions[str(experiment.dataset_id)] == pinned


def test_a_copy_shares_its_sources_scripts(api, student_a, project):
    source = make_run(student_a, project)
    response = api(student_a).post(
        URL, {"title": "复制", "script_dataset_id": source.script_dataset_id}, format="json"
    )
    assert response.status_code == 201, response.json()
    copy = ProcessingRun.objects.get(pk=response.json()["id"])
    assert copy.script_dataset_id == source.script_dataset_id
    assert copy.output_dataset_id not in (None, source.output_dataset_id)
    assert copy.project is None  # 项目 is optional


def test_dataset_kinds_are_checked(api, student_a, project):
    raw = make_dataset(student_a, project)
    response = api(student_a).post(
        URL,
        {"project_id": project.pk, "title": "t", "script_dataset_id": raw.pk, "output_dataset_id": raw.pk},
        format="json",
    )
    assert response.status_code == 400
    assert set(response.json()["errors"]) == {"script_dataset_id", "output_dataset_id"}


def test_datasets_and_experiments_must_be_citable(api, student_a, student_b, project):
    run = make_run(student_a, project)
    fields = {
        "experiment_ids": [make_experiment(student_b, project).pk],  # a teammate's draft is not shared
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


def test_script_and_result_files_cannot_be_dropped(api, student_a, project):
    run = make_run(student_a, project)
    response = api(student_a).patch(f"{URL}{run.pk}/", {"script_dataset_id": None, "output_dataset_id": None}, format="json")
    assert response.status_code == 400
    assert set(response.json()["errors"]) == {"script_dataset_id", "output_dataset_id"}


def test_submit_lists_everything_missing(api, student_a, project):
    run = ProcessingRun.objects.create(owner=student_a, project=project, title="空记录")
    response = api(student_a).post(f"{URL}{run.pk}/submit/")
    assert response.status_code == 400
    assert set(response.json()["errors"]) == {"experiments", "script", "results"}
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


@pytest.mark.parametrize("how", ["uploaded script", "method", "git"])
def test_any_one_way_of_naming_the_algorithm_is_enough(api, student_a, project, how):
    """Origin / Excel / instrument software users write down what they did instead of uploading code."""
    run = make_run(student_a, project, script_repo="", script_commit="", environment="", conclusion="")
    add_file(run.output_dataset, "结果.csv")  # results: a file instead of a conclusion
    if how == "uploaded script":
        add_file(run.script_dataset, "process.m", b"% matlab")
    elif how == "method":
        ProcessingRun.objects.filter(pk=run.pk).update(method="Excel：按通道求均值")
    else:
        ProcessingRun.objects.filter(pk=run.pk).update(script_repo="https://git.example.com/x.git", script_commit="abc")
    response = api(student_a).post(f"{URL}{run.pk}/submit/")
    assert response.status_code == 200, response.json()  # 运行环境 is optional now


def test_list_has_no_n_plus_1(api, student_a, project, django_assert_max_num_queries):
    for _ in range(5):
        make_run(student_a, project)
    client = api(student_a)
    # session + user + count + page (with joined datasets) + inputs prefetch + experiments prefetch
    with django_assert_max_num_queries(6):
        assert client.get(URL).json()["count"] == 5
