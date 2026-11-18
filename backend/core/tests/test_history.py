import pytest

from equipment.models import Equipment
from projects.models import Project
from research.tests.factories import make_experiment

pytestmark = pytest.mark.django_db


def test_foreign_keys_show_names_not_ids(api, group, project, student_a, student_b, manager):
    device = Equipment.objects.create(group=group, code="UT-001", name="超声探伤仪")
    api(manager).patch(f"/api/equipment/{device.id}/", {"custodian_id": student_b.id}, format="json")
    changes = api(student_a).get(f"/api/equipment/{device.id}/history/").data[0]["changes"]
    # A member shows as their name: the student id (username) is private to supervisors.
    assert {"field": "custodian", "old": None, "new": student_b.name} in changes

    other = Project.objects.create(group=group, name="相控阵成像", leader=student_a)
    experiment = make_experiment(student_a, project)
    body = {"equipment_item_id": device.id, "project_id": other.id}
    api(student_a).patch(f"/api/experiments/{experiment.id}/", body, format="json")
    changes = api(student_a).get(f"/api/experiments/{experiment.id}/history/").data[0]["changes"]
    assert {"field": "equipment_item", "old": None, "new": "UT-001 超声探伤仪"} in changes
    assert {"field": "project", "old": project.name, "new": "相控阵成像"} in changes
