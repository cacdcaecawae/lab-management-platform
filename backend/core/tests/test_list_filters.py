"""List filters, sorting and code search added for issue #48 (S2, S3), across the modules that use core.filters."""
import datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from achievements.models import Achievement
from equipment.models import Booking, Equipment
from inventory.models import Consumable, StockTxn
from meetings.models import AgendaItem, Meeting
from procurement.models import Fund, PurchaseItem, PurchaseRequest, Reimbursement
from research.models import Experiment
from specimens.models import Specimen

pytestmark = pytest.mark.django_db


def names(response, key="name"):
    assert response.status_code == 200, response.content
    return [row[key] for row in response.data["results"]]


def test_equipment_filters_and_sorting(api, group, other_group, student_a, manager):
    a = Equipment.objects.create(group=group, code="UT-002", name="探伤仪", category="探伤仪", location="A302", custodian=manager)
    b = Equipment.objects.create(group=group, code="UT-001", name="探头", category="探头", location="A302")
    Equipment.objects.create(group=other_group, code="UT-000", name="外组", category="探伤仪", location="A302")
    now = timezone.now()
    Booking.objects.create(equipment=b, user=student_a, start_at=now - datetime.timedelta(hours=1), end_at=now + datetime.timedelta(hours=1))
    client = api(student_a)
    assert names(client.get("/api/equipment/", {"category": "探伤仪"})) == [a.name]
    assert names(client.get("/api/equipment/", {"location": "A302", "ordering": "code"})) == [b.name, a.name]
    assert names(client.get("/api/equipment/", {"ordering": "-code"})) == [a.name, b.name]
    assert names(client.get("/api/equipment/", {"custodian": manager.pk})) == [a.name]
    assert names(client.get("/api/equipment/", {"idle": "1"})) == [a.name]
    for odd in ({"custodian": "x"}, {"location": "A\x00"}, {"ordering": "notes\x00"}):
        assert client.get("/api/equipment/", odd).status_code == 200


def test_specimen_and_consumable_filters(api, group, student_a, manager):
    Specimen.objects.create(group=group, code="S-1", name="钢块", material="20 钢", location="柜 1", defects_public=True)
    Specimen.objects.create(group=group, code="S-2", name="铝块", material="6061 铝", location="柜 2")
    assert names(api(student_a).get("/api/specimens/", {"material": "20 钢"})) == ["钢块"]
    assert names(api(manager).get("/api/specimens/", {"defects_public": "0"})) == ["铝块"]
    assert names(api(manager).get("/api/specimens/", {"ordering": "-code"})) == ["铝块", "钢块"]

    gel = Consumable.objects.create(group=group, name="耦合剂", category="耗材", location="A302")
    cable = Consumable.objects.create(group=group, name="线缆", category="配件")
    StockTxn.objects.create(consumable=gel, kind=StockTxn.Kind.IN, quantity=1, handler=manager)
    StockTxn.objects.create(consumable=cable, kind=StockTxn.Kind.IN, quantity=5, handler=manager)
    client = api(student_a)
    assert names(client.get("/api/consumables/", {"category": "配件"})) == ["线缆"]
    assert names(client.get("/api/consumables/", {"location": "A302"})) == ["耦合剂"]
    assert names(client.get("/api/consumables/", {"ordering": "-stock"})) == ["线缆", "耦合剂"]
    assert client.get("/api/consumables/", {"ordering": "nearest_expiry_on"}).status_code == 200


def purchase(owner, fund, price, purpose="探头"):
    request = PurchaseRequest.objects.create(owner=owner, fund=fund, purpose=purpose)
    PurchaseItem.objects.create(request=request, name=purpose, quantity=2, unit_price=Decimal(price))
    return request


def test_purchases_by_fund_owner_code_and_total(api, group, other_group, student_a, student_b, manager, other_manager):
    fund = Fund.objects.create(group=group, code="F-1", name="面上", owner=manager)
    other = Fund.objects.create(group=group, code="F-2", name="横向")
    cheap = purchase(student_a, fund, "10.00", "耦合剂")
    dear = purchase(student_b, other, "500.00", "探头")
    elsewhere = purchase(other_manager, Fund.objects.create(group=other_group, code="X", name="外组"), "1.00")
    client = api(manager)
    assert names(client.get("/api/purchases/", {"fund": fund.pk}), "purpose") == ["耦合剂"]
    assert names(client.get("/api/purchases/", {"owner": student_b.pk}), "purpose") == ["探头"]
    assert names(client.get("/api/purchases/", {"ordering": "total_amount"}), "purpose") == ["耦合剂", "探头"]
    assert names(client.get("/api/purchases/", {"ordering": "-total_amount"}), "purpose") == ["探头", "耦合剂"]
    assert names(client.get("/api/purchases/", {"search": dear.code.lower()}), "purpose") == ["探头"]
    assert names(client.get("/api/purchases/", {"search": elsewhere.code}), "purpose") == []  # another group's code
    assert names(api(student_a).get("/api/purchases/", {"search": dear.code}), "purpose") == []  # not mine
    assert names(api(student_a).get("/api/purchases/", {"search": cheap.code}), "purpose") == ["耦合剂"]
    assert names(client.get("/api/funds/", {"owner": manager.pk}), "code") == ["F-1"]
    assert client.get("/api/purchases/", {"fund": "1\x00"}).data["count"] == 0


def test_reimbursement_search_shared_by_list_and_stats(api, group, student_a, manager, advisor):
    fund = Fund.objects.create(group=group, code="F-1", name="面上")
    first = Reimbursement.objects.create(owner=student_a, fund=fund, amount=Decimal("30.00"), occurred_on=datetime.date(2026, 11, 2), description="打车")
    Reimbursement.objects.create(owner=manager, fund=fund, amount=Decimal("120.00"), occurred_on=datetime.date(2026, 11, 9), description="耦合剂")
    client = api(advisor)
    assert names(client.get("/api/reimbursements/", {"search": "打车"}), "description") == ["打车"]
    assert names(client.get("/api/reimbursements/", {"search": first.code}), "description") == ["打车"]
    assert names(client.get("/api/reimbursements/", {"search": "管理员"}), "description") == []
    assert names(client.get("/api/reimbursements/", {"ordering": "amount"}), "description") == ["打车", "耦合剂"]
    assert names(client.get("/api/reimbursements/", {"from": "2026-11-05", "to": "2026-11-30"}), "description") == ["耦合剂"]
    stats = client.get("/api/reimbursements/stats/", {"search": "打车"}).data
    assert (stats["count"], stats["total"]) == (1, "30.00")


def test_research_codes_and_sorting(api, student_a, student_b, project, advisor):
    old = Experiment.objects.create(owner=student_a, project=project, title="旧", date=datetime.date(2026, 1, 5))
    new = Experiment.objects.create(owner=student_a, project=project, title="新", date=datetime.date(2026, 11, 5))
    theirs = Experiment.objects.create(owner=student_b, project=project, title="别人的", date=datetime.date(2026, 6, 5))
    client = api(student_a)
    assert names(client.get("/api/experiments/", {"search": old.code}), "title") == ["旧"]
    assert names(client.get("/api/experiments/", {"search": theirs.code}), "title") == []
    assert names(client.get("/api/experiments/", {"search": old.code.replace("EX", "RUN")}), "title") == []
    assert names(client.get("/api/experiments/", {"ordering": "date"}), "title") == ["旧", "新"]
    assert names(api(advisor).get("/api/experiments/", {"ordering": "-date"}), "title") == ["新", "别人的", "旧"]
    assert names(client.get("/api/experiments/", {"search": f"EX-1999-{new.pk:04d}"}), "title") == []


def test_meeting_search_and_achievement_fulltext(api, group, student_a, manager):
    talk = Meeting.objects.create(group=group, date=datetime.date(2026, 11, 2), created_by=manager)
    AgendaItem.objects.create(meeting=talk, presenter=student_a, topic="导波成像")
    Meeting.objects.create(group=group, date=datetime.date(2026, 11, 9), created_by=manager, minutes="讨论采购")
    client = api(student_a)
    assert names(client.get("/api/meetings/", {"search": "导波"}), "date") == ["2026-11-02"]
    assert names(client.get("/api/meetings/", {"search": "s_a"}), "date") == ["2026-11-02"]
    assert names(client.get("/api/meetings/", {"search": "采购"}), "date") == ["2026-11-09"]

    Achievement.objects.create(group=group, created_by=manager, type="paper", status="published", title="有全文", authors="甲", date=datetime.date(2026, 1, 1), fulltext="x.pdf")
    Achievement.objects.create(group=group, created_by=manager, type="paper", status="published", title="没全文", authors="甲", date=datetime.date(2026, 2, 1))
    assert names(client.get("/api/achievements/", {"has_fulltext": "1"}), "title") == ["有全文"]
    assert names(client.get("/api/achievements/", {"has_fulltext": "0"}), "title") == ["没全文"]
    assert names(client.get("/api/achievements/", {"ordering": "date"}), "title") == ["有全文", "没全文"]
