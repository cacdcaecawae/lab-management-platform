from datetime import date

import pytest

from achievements.models import Achievement
from conftest import make_user
from datasets.models import Dataset
from equipment.models import Equipment
from inventory.models import Consumable
from knowledge.models import Doc
from datasets.models import DataFile
from meetings.models import ActionItem, AgendaItem, Meeting
from procurement.models import Fund, PurchaseItem, PurchaseRequest, Reimbursement
from projects.models import Milestone, Project, Task
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
    research = {"experiments", "runs", "datasets", "reports"}
    private = research | {"purchases"}
    clients = [api(user) for user in (student_a, advisor, manager, other_manager)]
    for i, client in enumerate(clients):
        with django_assert_max_num_queries(25):  # one query per module (20), plus the session
            response = client.get(URL, {"q": "2030"})
        assert response.status_code == 200
        assert response["Cache-Control"] == "private, no-store"
        found = {group["module"]: [item["id"] for item in group["items"]] for group in response.data}
        expected = {
            key: [foreign[key].pk] if i == 3 else
            [own[key].pk] if i == 0 and key in private else
            [] if i == 2 and key in research else  # a student with the 管理员 tag: purchases, not research records
            [peer[key].pk, own[key].pk]
            for key in own
        }
        assert found == {key: ids for key, ids in expected.items() if ids}


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


def test_new_kinds_codes_and_who_sees_them(api, group, student_a, student_b, advisor, manager, other_manager, project):
    """Issue #48 N6: members, funds, reimbursements, tasks, milestones, action items, data files; codes; names."""
    Fund.objects.create(group=group, code="NSFC-7788", name="面上")
    bill = Reimbursement.objects.create(owner=student_b, fund=Fund.objects.get(code="NSFC-7788"), amount=1, occurred_on=DAY, description="打车7788")
    Task.objects.create(project=project, title="标定7788", created_by=student_a)
    Milestone.objects.create(project=project, title="中期7788")
    meeting = Meeting.objects.create(group=group, date=DAY, created_by=manager, minutes="讨论7788")
    AgendaItem.objects.create(meeting=meeting, presenter=student_a, topic="成像")
    ActionItem.objects.create(meeting=meeting, owner=student_a, content="补实验7788")
    data = Dataset.objects.create(owner=student_b, project=project, name="波形")
    DataFile.objects.create(dataset=data, name="wave7788.csv", size=1, sha256="0" * 64, uploaded_by=student_b)
    report = WeeklyReport.objects.create(owner=student_b, week_start=DAY)

    def found(user, q):
        return {g["module"]: g["items"] for g in api(user).get(URL, {"q": q}).data}

    mine = found(student_a, "7788")
    # not b's bill nor b's file; no funds either: only managers can open the 经费来源 page
    assert set(mine) == {"tasks", "milestones", "meetings", "actions"}
    assert found(manager, "7788")["funds"][0]["link"] == "/funds"
    assert mine["tasks"][0]["link"] == f"/projects/{project.pk}?tab=tasks"
    assert mine["actions"][0]["link"] == f"/meetings/{meeting.pk}"
    assert mine["meetings"][0]["subtitle"] == DAY.isoformat()
    assert set(found(advisor, "7788")) >= {"reimbursements", "files"}
    assert found(advisor, "7788")["files"][0]["link"] == f"/datasets/{data.pk}"
    assert found(manager, bill.code)["reimbursements"][0]["link"] == f"/reimbursements?item={bill.pk}"
    assert found(other_manager, "7788") == {}
    # weekly reports by the student's name; login names only for advisors and managers
    assert found(advisor, "s_b")["reports"][0] == {"id": report.pk, "title": str(DAY), "subtitle": "s_b", "link": f"/reports/{report.pk}"}
    student_b.name = "陈同学"
    student_b.save()
    assert "members" not in found(student_a, "s_b") and "members" in found(advisor, "s_b")
    assert [m["title"] for m in found(student_a, "陈同学")["members"]] == ["陈同学"]
    make_user("s_apply", group, pending=True, is_active=False, name="陈申请")  # an applicant is not a member yet
    assert "members" not in found(advisor, "陈申请")
