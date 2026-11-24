"""Issue #48 N7: the group ledger across consumables, its filters and its export."""
import io

import pytest
from openpyxl import load_workbook

from inventory.models import Consumable, StockTxn

pytestmark = pytest.mark.django_db


@pytest.fixture
def ledger(group, other_group, student_a, student_b, manager, other_manager, project):
    gel = Consumable.objects.create(group=group, name="耦合剂", unit="瓶")
    cable = Consumable.objects.create(group=group, name="线缆", unit="根")
    StockTxn.objects.create(consumable=gel, kind=StockTxn.Kind.IN, quantity=10, handler=manager)
    StockTxn.objects.create(consumable=cable, kind=StockTxn.Kind.IN, quantity=3, handler=manager)
    StockTxn.objects.create(consumable=gel, kind=StockTxn.Kind.OUT, quantity=-2, handler=student_a, project=project)
    StockTxn.objects.create(consumable=gel, kind=StockTxn.Kind.OUT, quantity=-1, handler=student_b)
    foreign = Consumable.objects.create(group=other_group, name="外组")
    StockTxn.objects.create(consumable=foreign, kind=StockTxn.Kind.IN, quantity=1, handler=other_manager)
    return gel, cable


def test_who_sees_which_entries(api, ledger, student_a, manager, advisor):
    gel, _cable = ledger
    rows = api(manager).get("/api/stock-txns/").data["results"]
    assert [(r["consumable"]["name"], r["quantity"]) for r in rows] == [("耦合剂", -1), ("耦合剂", -2), ("线缆", 3), ("耦合剂", 10)]
    assert api(advisor).get("/api/stock-txns/").data["count"] == 4
    assert [r["quantity"] for r in api(student_a).get("/api/stock-txns/").data["results"]] == [-2]  # what they handled


def test_filters_and_export_agree(api, ledger, student_b, manager, project):
    gel, _cable = ledger
    client = api(manager)
    assert client.get("/api/stock-txns/", {"consumable": gel.pk, "kind": "out"}).data["count"] == 2
    assert client.get("/api/stock-txns/", {"handler": student_b.pk}).data["count"] == 1
    assert client.get("/api/stock-txns/", {"project": project.pk}).data["count"] == 1
    assert client.get("/api/stock-txns/", {"kind": "nope"}).data["count"] == 0
    assert client.get("/api/stock-txns/", {"from": "2026-13-45"}).status_code == 400
    response = client.get("/api/stock-txns/export/", {"kind": "out"})
    sheet = load_workbook(io.BytesIO(response.content)).active
    rows = list(sheet.iter_rows(min_row=2, values_only=True))
    assert [(r[1], r[3], r[5], r[7]) for r in rows] == [("耦合剂", "领用", -1, "s_b"), ("耦合剂", "领用", -2, "s_a")]
