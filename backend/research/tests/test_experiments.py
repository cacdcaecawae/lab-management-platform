import pytest

from projects.models import Project
from research.models import Experiment

from .factories import make_dataset, make_experiment

pytestmark = pytest.mark.django_db

URL = "/api/experiments/"


def body(project, **extra):
    return {"project_id": project.pk, "title": "螺栓预紧力 A 组", "date": "2026-11-16", **extra}


def test_create_experiment(api, student_a, project):
    dataset = make_dataset(student_a, project)
    response = api(student_a).post(
        URL,
        body(project, equipment="导波采集仪", params={"频率": "100kHz"}, dataset_ids=[dataset.pk], status="submitted"),
        format="json",
    )
    assert response.status_code == 201, response.json()
    data = response.json()
    assert data["code"] == f"EX-2026-{data['id']:04d}"
    assert data["status"] == "draft" and data["submitted_at"] is None
    assert data["owner"] == {"id": student_a.pk, "name": student_a.name}
    assert data["project"] == {"id": project.pk, "name": project.name}
    assert data["params"] == {"频率": "100kHz"}
    assert data["datasets"] == [{"id": dataset.pk, "code": dataset.code, "name": dataset.name, "kind": "raw", "version": None, "changed": False}]


def test_datasets_must_belong_to_the_owner(api, student_a, student_b, manager, project):
    theirs = make_dataset(student_b, project)
    for user, dataset_id in ((student_a, theirs.pk), (student_a, 999999), (manager, theirs.pk)):
        response = api(user).post(URL, body(project, dataset_ids=[dataset_id]), format="json")
        assert response.status_code == 400
        assert "dataset_ids" in response.json()["errors"]


def test_equipment_item_from_my_group(api, student_a, project, group, other_group):
    from equipment.models import Equipment

    mine = Equipment.objects.create(group=group, code="UT-001", name="超声探伤仪")
    outside = Equipment.objects.create(group=other_group, code="UT-001", name="外组的")
    response = api(student_a).post(URL, body(project, equipment_item_id=outside.pk), format="json")
    assert response.status_code == 400 and "equipment_item_id" in response.json()["errors"]
    data = api(student_a).post(URL, body(project, equipment_item_id=mine.pk, equipment="自带的前置放大器"), format="json").json()
    assert data["equipment_item"] == {"id": mine.pk, "code": "UT-001", "name": "超声探伤仪", "status": "available"}
    assert data["equipment"] == "自带的前置放大器"
    cleared = api(student_a).patch(f"{URL}{data['id']}/", {"equipment_item_id": None}, format="json").json()
    assert cleared["equipment_item"] is None


def test_project_must_be_in_my_group(api, student_a, other_group, other_manager):
    foreign = Project.objects.create(group=other_group, name="外组项目", leader=other_manager)
    response = api(student_a).post(URL, body(foreign), format="json")
    assert response.status_code == 400
    assert "project_id" in response.json()["errors"]


@pytest.mark.parametrize("params", [[1, 2], "100kHz", 3])
def test_params_must_be_an_object(api, student_a, project, params):
    response = api(student_a).post(URL, body(project, params=params), format="json")
    assert response.status_code == 400
    assert "params" in response.json()["errors"]

    experiment = make_experiment(student_a, project)
    response = api(student_a).patch(f"{URL}{experiment.pk}/", {"params": params}, format="json")
    assert response.status_code == 400
    assert "params" in response.json()["errors"]


def test_patch_replaces_datasets(api, student_a, project):
    experiment = make_experiment(student_a, project)
    experiment.datasets.add(make_dataset(student_a, project, name="旧"))
    new = make_dataset(student_a, project, name="新")
    response = api(student_a).patch(f"{URL}{experiment.pk}/", {"dataset_ids": [new.pk]}, format="json")
    assert response.status_code == 200
    assert [d["id"] for d in response.json()["datasets"]] == [new.pk]


def test_submit_reports_missing_title(api, student_a, project):
    experiment = make_experiment(student_a, project)
    Experiment.objects.filter(pk=experiment.pk).update(title="")  # the API itself never allows a blank title
    response = api(student_a).post(f"{URL}{experiment.pk}/submit/")
    assert response.status_code == 400
    assert list(response.json()["errors"]) == ["title"]


def test_list_has_no_n_plus_1(api, student_a, project, django_assert_max_num_queries):
    for _ in range(5):
        make_experiment(student_a, project).datasets.add(make_dataset(student_a, project))
    client = api(student_a)
    # session + user + count + page + datasets prefetch + specimens prefetch + photos prefetch
    with django_assert_max_num_queries(7):
        assert client.get(URL).json()["count"] == 5
