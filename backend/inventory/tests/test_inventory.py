import threading

import pytest
from django.db import connection

from inventory.models import Consumable, StockTxn
from inventory.serializers import StockTxnSerializer

pytestmark = pytest.mark.django_db


@pytest.fixture
def cable(group, manager):
    item = Consumable.objects.create(group=group, name="BNC 线", spec="1 m", unit="根", safety_stock=5)
    StockTxn.objects.create(consumable=item, kind="in", quantity=10, handler=manager)
    return item


def txn(client, item, kind, quantity, **extra):
    return client.post(f"/api/consumables/{item.id}/txns/", {"kind": kind, "quantity": quantity, **extra})


def stock(client, item):
    return client.get(f"/api/consumables/{item.id}/").data["stock"]


def test_only_managers_maintain_items(api, group, student_a, advisor, manager, cable):
    body = {"name": "耦合剂", "spec": "250 mL", "unit": "瓶", "safety_stock": 2}
    assert api(student_a).post("/api/consumables/", body).status_code == 403
    assert api(advisor).post("/api/consumables/", body).status_code == 403
    r = api(manager).post("/api/consumables/", body)
    assert r.status_code == 201 and r.data["stock"] == 0 and r.data["low"] is True
    assert Consumable.objects.get(pk=r.data["id"]).group == group
    assert api(manager).post("/api/consumables/", body).status_code == 409  # same name + spec
    assert api(manager).post("/api/consumables/", {**body, "spec": "500 mL"}).status_code == 201
    assert api(manager).patch(f"/api/consumables/{cable.id}/", {"spec": "250 mL", "name": "耦合剂"}).status_code == 409
    assert api(student_a).patch(f"/api/consumables/{cable.id}/", {"safety_stock": 1}).status_code == 403


def test_take_out_reduces_stock_and_cannot_go_negative(api, student_a, project, cable):
    client = api(student_a)
    r = txn(client, cable, "out", 3, project_id=project.id, note="螺栓实验")
    assert r.status_code == 201 and r.data["quantity"] == -3 and r.data["handler"]["id"] == student_a.id
    assert r.data["project"]["id"] == project.id
    assert stock(client, cable) == 7
    r = txn(client, cable, "out", 8)
    assert r.status_code == 400 and "库存不足" in r.data["errors"]["quantity"][0]
    assert stock(client, cable) == 7
    assert txn(client, cable, "return", 1).data["quantity"] == 1
    assert stock(client, cable) == 8


def test_quantity_rules(api, student_a, manager, cable):
    assert txn(api(student_a), cable, "out", 0).status_code == 400
    assert txn(api(student_a), cable, "out", -2).status_code == 400
    assert txn(api(manager), cable, "adjust", 0).status_code == 400
    assert txn(api(manager), cable, "adjust", -2).data["quantity"] == -2
    assert txn(api(manager), cable, "adjust", -9).status_code == 400  # stock would be -1


def test_stock_in_and_adjust_are_manager_only(api, student_a, advisor, manager, cable):
    assert txn(api(student_a), cable, "in", 5).status_code == 403
    assert txn(api(student_a), cable, "adjust", 1).status_code == 403
    assert txn(api(advisor), cable, "in", 5).status_code == 403
    assert txn(api(manager), cable, "in", 5).status_code == 201
    assert stock(api(manager), cable) == 15


def test_transactions_are_listed_newest_first(api, student_a, cable):
    txn(api(student_a), cable, "out", 2)
    r = api(student_a).get(f"/api/consumables/{cable.id}/txns/")
    assert [t["kind"] for t in r.data["results"]] == ["out", "in"]
    assert api(student_a).patch(f"/api/consumables/{cable.id}/txns/", {}).status_code == 405


def test_low_stock_filter_and_workbench(api, student_a, manager, advisor, cable):
    assert api(manager).get("/api/consumables/", {"low": 1}).data["count"] == 0
    txn(api(student_a), cable, "out", 6)
    low = api(manager).get("/api/consumables/", {"low": 1}).data["results"]
    assert [(c["name"], c["stock"], c["low"]) for c in low] == [("BNC 线", 4, True)]
    dash = api(manager).get("/api/dashboard/").data["manager"]
    assert [(c["name"], c["stock"]) for c in dash["low_stock"]] == [("BNC 线", 4)]
    assert api(advisor).get("/api/dashboard/").data["manager"] is None


def test_other_group_gets_404(api, other_manager, cable):
    client = api(other_manager)
    assert client.get("/api/consumables/").data["count"] == 0
    assert client.get(f"/api/consumables/{cable.id}/").status_code == 404
    assert txn(client, cable, "in", 5).status_code == 404
    assert client.get(f"/api/consumables/{cable.id}/txns/").status_code == 404


@pytest.mark.django_db(transaction=True)
def test_concurrent_take_outs_cannot_both_pass_the_stock_check(api, monkeypatch, student_a, student_b, cable):
    """Each request waits (up to 1 s) for the other between its stock check and its write. With the row lock the second
    request cannot even check until the first commits, so it sees the new stock; without it, both would pass."""
    checked, results = threading.Barrier(2, timeout=1), {}
    save = StockTxnSerializer.save

    def paused_save(serializer, **kwargs):
        try:
            checked.wait()
        except threading.BrokenBarrierError:
            pass  # the other request is waiting for the lock: expected
        return save(serializer, **kwargs)

    monkeypatch.setattr(StockTxnSerializer, "save", paused_save)

    def run(user):
        try:
            results[user.username] = txn(api(user), cable, "out", 10).status_code
        finally:
            connection.close()

    threads = [threading.Thread(target=run, args=(u,)) for u in (student_a, student_b)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(15)
    assert sorted(results.values()) == [201, 400]
    assert stock(api(student_a), cable) == 0
