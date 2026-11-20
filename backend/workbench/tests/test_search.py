from datetime import date

import pytest

from achievements.models import Achievement
from datasets.models import Dataset
from equipment.models import Equipment
from inventory.models import Consumable
from knowledge.models import Doc
from meetings.models import Meeting
from procurement.models import PurchaseItem, PurchaseRequest
from projects.models import Project
from reports.models import WeeklyReport
from research.models import Experiment, ProcessingRun
from specimens.models import Specimen, Defect

pytestmark = pytest.mark.django_db
URL = "/api/search/"
DAY = date(2030, 1, 7)


def catalog(user, marker):
    project = Project.objects.create(group=user.group, name=marker, leader=user)
    purchase = PurchaseRequest.objects.create(owner=user, purpose=marker)
    return {
        "projects": project,
        "experiments": Experiment.objects.create(owner=user, project=project, title=marker, date=DAY),
        "runs": ProcessingRun.objects.create(owner=user, project=project, title=marker),
        "datasets": Dataset.objects.create(owner=user, project=project, name=marker),
        "reports": WeeklyReport.objects.create(owner=user, week_start=DAY),
        "purchases": purchase,
        "equipment": Equipment.objects.create(group=user.group, name=marker, code=marker),
        "specimens": Specimen.objects.create(group=user.group, name=marker, code=marker),
        "consumables": Consumable.objects.create(group=user.group, name=marker),
        "knowledge": Doc.objects.create(group=user.group, title=marker, author=user),
        "meetings": Meeting.objects.create(group=user.group, title=marker, date=DAY, created_by=user),
        "achievements": Achievement.objects.create(group=user.group, title=marker, date=DAY, created_by=user),
    }


def test_all_module_scopes(api, student_a, student_b, advisor, manager, other_manager, django_assert_max_num_queries):
    own = catalog(student_a, "2030-A")
    peer = catalog(student_b, "2030-B")
    foreign = catalog(other_manager, "2030-C")
    private = {"experiments", "runs", "datasets", "reports", "purchases"}
    clients = [api(user) for user in (student_a, advisor, manager, other_manager)]
    for i, client in enumerate(clients):
        with django_assert_max_num_queries(15):
            response = client.get(URL, {"q": "2030"})
        assert response.status_code == 200
        assert response["Cache-Control"] == "private, no-store"
        found = {group["module"]: [item["id"] for item in group["items"]] for group in response.data}
        assert found == {
            key: [foreign[key].pk] if i == 3 else
            [own[key].pk] if i == 0 and key in private else [peer[key].pk, own[key].pk]
            for key in own
        }


def test_bounds_stability_and_blind_fields(api, student_a):
    rows = [Specimen.objects.create(group=student_a.group, name=f"试块{i}", code=f"AX{i}") for i in range(7)]
    Defect.objects.create(specimen=rows[0], kind=Defect.Kind.CRACK, note="隐藏缺陷")
    client = api(student_a)
    assert client.get(URL, {"q": "隐藏缺陷"}).data == []
    found = client.get(URL, {"q": " AX "}).data[0]["items"]
    assert [row["id"] for row in found] == [row.pk for row in rows[::-1][:5]]
    assert set(found[0]) == {"id", "title", "subtitle", "link"}
    for q in ("", " a ", "字" * 101):
        assert client.get(URL, {"q": q}).status_code == 400


def test_purchase_matches_items_without_duplicate(api, student_a):
    purchase = PurchaseRequest.objects.create(owner=student_a, purpose="采购")
    for suffix in ("甲", "乙"):
        PurchaseItem.objects.create(request=purchase, name="试块" + suffix, quantity=1, unit_price=1)
    assert [r["id"] for r in api(student_a).get(URL, {"q": "试块"}).data[0]["items"]] == [purchase.id]


def test_requires_active_group_member(api, ops, student_a):
    assert api().get(URL, {"q": "abc"}).status_code == 403
    assert api(ops).get(URL, {"q": "abc"}).status_code == 403
    student_a.must_change_password = True
    student_a.save()
    assert api(student_a).get(URL, {"q": "abc"}).status_code == 403


@pytest.mark.parametrize(("key", "endpoint"), [
    ("achievements", "/api/achievements/"),
    ("consumables", "/api/consumables/"),
])
def test_list_links_focus_exact_id_with_existing_filters(api, student_a, other_manager, key, endpoint):
    local = catalog(student_a, "2029-Match")[key]
    foreign = catalog(other_manager, "2029-Match")[key]
    client = api(student_a)
    found = {g["module"]: g["items"] for g in client.get(URL, {"q": "Match"}).data}
    assert found[key][0]["link"] == f"/{key}?item={local.pk}"
    # Search and status filters from a previous list visit cannot mask an exact item.
    for row, expected in ((local, [local.pk]), (foreign, [])):
        r = client.get(endpoint, {"item": row.pk, "search": "no match", "low": 1, "status": "nonexistent"})
        assert r.status_code == 200
        assert [item["id"] for item in r.data["results"]] == expected
