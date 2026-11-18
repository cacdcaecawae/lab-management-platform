from django.contrib import admin
import pytest

from inventory.admin import StockTxnInline
from inventory.models import Consumable, StockTxn

pytestmark = pytest.mark.django_db


def test_stocktake_requires_version_and_rejects_old_and_aba(api, group, manager):
    item = Consumable.objects.create(group=group, name="test")
    client = api(manager)
    url = f"/api/consumables/{item.pk}/txns/"
    detail = f"/api/consumables/{item.pk}/"
    assert client.get(detail).data["stock_version"] == 0
    # Empty-ledger stocktake, followed by ordinary writes, needs no migration or bootstrap row.
    assert client.post(url, {"kind": "adjust", "quantity": 10, "stock_version_seen": 0}).status_code == 201
    seen = client.get(detail).data["stock_version"]
    missing = client.post(url, {"kind": "adjust", "quantity": -2})
    assert missing.status_code == 400 and "stock_version_seen" in missing.data["errors"]
    payload = {"kind": "adjust", "quantity": -2, "stock_version_seen": seen}
    assert client.post(url, payload).status_code == 201
    assert client.post(url, payload).status_code == 409
    assert client.get(detail).data["stock"] == 8
    seen = client.get(detail).data["stock_version"]
    assert client.post(url, {"kind": "out", "quantity": 1}).status_code == 201
    assert client.post(url, {"kind": "return", "quantity": 1}).status_code == 201
    assert client.get(detail).data["stock"] == 8
    before = item.txns.count()
    response = client.post(url, {**payload, "stock_version_seen": seen})
    assert response.status_code == 409 and response.data["code"] == "stale_stock"
    assert item.txns.count() == before
    current = client.get(detail).data["stock_version"]
    assert client.post(url, {**payload, "stock_version_seen": current}).status_code == 201
    assert client.get(detail).data["stock"] == 6


def test_stocktake_unrelated_ledger_does_not_stale_version(api, group, manager):
    client = api(manager)
    a = Consumable.objects.create(group=group, name="a")
    b = Consumable.objects.create(group=group, name="b")
    assert client.post(f"/api/consumables/{b.pk}/txns/", {"kind": "in", "quantity": 10}).status_code == 201
    assert client.post(f"/api/consumables/{a.pk}/txns/", {
        "kind": "adjust", "quantity": 2, "stock_version_seen": 0,
    }).status_code == 201


def test_admin_ledger_is_read_only_even_for_superuser(rf, ops):
    request = rf.get("/admin/")
    request.user = ops
    inline = StockTxnInline(Consumable, admin.site)
    assert inline.has_view_permission(request)
    assert not inline.has_add_permission(request)
    assert not inline.has_change_permission(request)
    assert not inline.has_delete_permission(request)
    assert set(inline.fields) <= set(inline.readonly_fields)


@pytest.mark.django_db(transaction=True)
def test_concurrent_stocktakes_only_one_accepts_same_version(api, group, manager, monkeypatch):
    import threading
    from django.db import connection
    from inventory.serializers import StockTxnSerializer

    item = Consumable.objects.create(group=group, name="concurrent")
    entry = StockTxn.objects.create(consumable=item, handler=manager, kind="in", quantity=10)
    checked, results = threading.Barrier(2, timeout=1), []
    original = StockTxnSerializer.save

    def paused_save(serializer, **kwargs):
        try:
            checked.wait()
        except threading.BrokenBarrierError:
            pass  # With the row lock, the other request waits until this transaction commits.
        return original(serializer, **kwargs)

    monkeypatch.setattr(StockTxnSerializer, "save", paused_save)

    def run():
        try:
            response = api(manager).post(f"/api/consumables/{item.pk}/txns/", {
                "kind": "adjust", "quantity": -2, "stock_version_seen": entry.pk,
            })
            results.append(response.status_code)
        finally:
            connection.close()

    workers = [threading.Thread(target=run) for _ in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(15)
    assert not any(worker.is_alive() for worker in workers)
    assert sorted(results) == [201, 409]
    assert item.txns.count() == 2
    assert api(manager).get(f"/api/consumables/{item.pk}/").data["stock"] == 8


def test_dashboard_low_stock_exposes_same_ledger_version(api, group, manager):
    item = Consumable.objects.create(group=group, name="low", safety_stock=100)
    entry = StockTxn.objects.create(consumable=item, handler=manager, kind="in", quantity=1)
    rows = api(manager).get("/api/dashboard/").data["manager"]["low_stock"]
    row = next(row for row in rows if row["id"] == item.pk)
    assert row["stock_version"] == entry.pk
    assert row["stock"] == 1
