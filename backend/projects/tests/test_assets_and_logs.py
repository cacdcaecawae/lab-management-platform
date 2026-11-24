"""Issue #48 N5: project members write progress logs; the lists a project's 资产 tab reads, filtered by project."""
import datetime

import pytest
from django.utils import timezone

from conftest import make_user
from equipment.models import Booking, Equipment
from inventory.models import Consumable, StockTxn
from projects.models import Project
from research.models import Experiment
from specimens.models import Specimen, SpecimenLoan

pytestmark = pytest.mark.django_db


def test_members_write_progress_logs(api, group, project, student_a, student_b, advisor):
    outsider = make_user("s_c", group)
    body = {"date": "2026-11-23", "content": "完成标定"}
    assert api(student_b).post(f"/api/projects/{project.pk}/logs/", body).status_code == 201  # a member, not the leader
    assert api(advisor).post(f"/api/projects/{project.pk}/logs/", body).status_code == 201
    refused = api(outsider).post(f"/api/projects/{project.pk}/logs/", body)
    assert refused.status_code == 403 and refused.data["message"] == "仅本项目成员、管理员或导师可以写进展"
    assert api(student_b).patch(f"/api/projects/{project.pk}/", {"name": "改名"}).status_code == 403  # logs only


def test_asset_lists_by_project(api, group, other_group, project, student_a, student_b, advisor, manager, other_manager):
    other = Project.objects.create(group=group, name="别的项目", leader=student_a)
    Experiment.objects.create(owner=student_a, project=project, title="甲的", date=datetime.date(2026, 11, 2))
    Experiment.objects.create(owner=student_b, project=project, title="乙的", date=datetime.date(2026, 11, 3))
    Experiment.objects.create(owner=student_a, project=other, title="别的", date=datetime.date(2026, 11, 4))
    device = Equipment.objects.create(group=group, code="UT", name="探伤仪")
    start = timezone.now() + datetime.timedelta(days=1)
    Booking.objects.create(equipment=device, user=student_a, project=project, start_at=start, end_at=start + datetime.timedelta(hours=1))
    Booking.objects.create(equipment=device, user=student_a, start_at=start + datetime.timedelta(hours=2), end_at=start + datetime.timedelta(hours=3))
    block = Specimen.objects.create(group=group, code="S-1", name="试块")
    SpecimenLoan.objects.create(specimen=block, borrower=student_b, project=project)
    gel = Consumable.objects.create(group=group, name="耦合剂")
    StockTxn.objects.create(consumable=gel, kind=StockTxn.Kind.IN, quantity=5, handler=manager)
    StockTxn.objects.create(consumable=gel, kind=StockTxn.Kind.OUT, quantity=-1, handler=student_b, project=project)

    def count(user, url):
        return api(user).get(url, {"project": project.pk}).data["count"]

    assert count(student_a, "/api/experiments/") == 1 and count(advisor, "/api/experiments/") == 2  # own vs. group
    assert count(student_a, "/api/bookings/all/") == 1
    loans = api(student_a).get("/api/specimen-loans/", {"project": project.pk}).data["results"]
    assert [(loan["specimen"]["code"], loan["borrower"]["name"]) for loan in loans] == [("S-1", "s_b")]
    assert count(advisor, "/api/stock-txns/") == 1 and count(student_a, "/api/stock-txns/") == 0  # not their take-out
    assert count(other_manager, "/api/specimen-loans/") == 0 and count(other_manager, "/api/bookings/all/") == 0
