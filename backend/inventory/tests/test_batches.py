from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from django.db import connection
from django.utils import timezone

from inventory.models import Consumable, StockTxn

pytestmark = pytest.mark.django_db


def paths(item):
    detail = f"/api/consumables/{item.pk}/"
    return detail, detail + "txns/", detail + "batch-mode/"


def switch(client, item, enabled, **extra):
    detail, _, mode = paths(item)
    seen = client.get(detail).data["stock_version"]
    return client.post(mode, {"stock_version_seen": seen, "tracks_batches": enabled, **extra}, format="json")


def test_opening_transfer_is_atomic_and_zero_net(api, manager, group):
    item = Consumable.objects.create(group=group, name="耦合剂")
    client = api(manager)
    detail, txns, mode = paths(item)
    original = client.post(txns, {"kind": "in", "quantity": 10}).data["id"]
    assert switch(client, item, True).data["code"] == "opening_batch_required"
    assert item.txns.count() == 1
    row = switch(client, item, True, opening_batch={"batch_no": "初始一"}).data
    assert row["stock"] == 10 and row["stock_version"] > original
    assert row["batches"][0]["stock"] == 10
    assert list(item.txns.order_by("id").values_list("kind", "quantity", "batch_id")) == [
        ("in", 10, None), ("allocation", -10, None), ("allocation", 10, row["batches"][0]["id"]), ("batch_mode", 0, None),
    ]
    assert client.post(mode, {"stock_version_seen": original, "tracks_batches": False}).status_code == 409
    assert switch(client, item, False).data["code"] == "batches_not_empty"
    assert client.get(detail).data["tracks_batches"]


def test_zero_toggle_aba_stales_old_stocktake_without_deleting_zero_batches(api, manager, group):
    item = Consumable.objects.create(group=group, name="耦合剂")
    client = api(manager)
    detail, txns, _ = paths(item)
    first = client.get(detail).data["stock_version"]
    assert switch(client, item, True).status_code == 200
    assert switch(client, item, False).status_code == 200
    now = client.get(detail).data
    assert not now["tracks_batches"] and now["stock"] == 0 and now["stock_version"] > first
    assert client.post(txns, {"kind": "adjust", "quantity": 1, "stock_version_seen": first}).data["code"] == "stale_stock"


def test_batch_rules_permissions_and_returns(api, manager, student_a, group, other_manager):
    item = Consumable.objects.create(group=group, name="耦合剂")
    foreign = Consumable.objects.create(group=other_manager.group, name="耦合剂")
    client = api(manager)
    student = api(student_a)
    detail, txns, mode = paths(item)
    assert api(other_manager).get(detail).status_code == 404
    assert api(other_manager).post(mode, {"stock_version_seen": 0, "tracks_batches": True}).status_code == 404
    assert student.post(mode, {"stock_version_seen": 0, "tracks_batches": True}).status_code == 403
    assert client.patch(detail, {"tracks_batches": True}).data["tracks_batches"] is False
    assert switch(client, item, True).status_code == 200
    assert client.post(txns, {"kind": "in", "quantity": 1}).status_code == 400
    assert student.post(txns, {"kind": "out", "quantity": 1}).status_code == 400
    assert client.post(txns, {"kind": "batch_mode", "quantity": 0}).status_code == 400
    assert client.post(txns, {"kind": "allocation", "quantity": 1}).status_code == 400
    alien_batch = foreign.batches.create(batch_no="外组")
    assert student.post(txns, {"kind": "return", "quantity": 1, "batch_id": alien_batch.pk}).status_code == 400

    today = timezone.localdate()
    expired = (today - timedelta(days=1)).isoformat()
    assert client.post(txns, {"kind": "in", "quantity": 1, "batch_no": "expired", "expires_on": expired}).status_code == 201
    assert client.post(txns, {"kind": "in", "quantity": 1, "batch_no": "today", "expires_on": today.isoformat()}).status_code == 201
    assert client.post(txns, {"kind": "in", "quantity": 8, "batch_no": "undated"}).status_code == 201
    assert client.post(txns, {"kind": "in", "quantity": 9, "batch_no": "today", "expires_on": expired}).status_code == 400
    result = client.get(detail).data
    expired_batch, today_batch, _ = result["batches"]
    assert result["stock"] == 10 and result["nearest_expiry"] == expired
    assert not expired_batch["can_issue"] and today_batch["can_issue"]
    assert student.post(txns, {"kind": "out", "quantity": 1, "batch_id": expired_batch["id"]}).status_code == 400
    assert student.post(txns, {"kind": "out", "quantity": 2, "batch_id": today_batch["id"]}).status_code == 400
    assert student.post(txns, {"kind": "out", "quantity": 1, "batch_id": today_batch["id"]}).status_code == 201
    assert client.get(detail).data["batches"][1]["stock"] == 0
    assert student.post(txns, {"kind": "return", "quantity": 1, "batch_id": today_batch["id"]}).status_code == 201
    seen = client.get(detail).data["stock_version"]
    assert client.post(txns, {"kind": "adjust", "quantity": -1, "batch_id": expired_batch["id"], "stock_version_seen": seen}).status_code == 201
    dashboard = client.get("/api/dashboard/").json()["manager"]["expiring_batches"]
    assert [b["batch_no"] for b in dashboard] == ["today"]
    listed = client.get("/api/consumables/?expiring_within=0")
    assert [c["id"] for c in listed.data["results"]] == [item.id]
    assert client.get("/api/consumables/?expiring_within=-1").status_code == 400


def test_post_migration_legacy_insert_gets_default_off(api, group, manager):
    # Old binaries omit this new NOT NULL column from INSERT, so the schema must supply a persistent default.
    with connection.cursor() as cursor:
        cursor.execute("""
            INSERT INTO inventory_consumable
            (group_id, name, spec, unit, location, safety_stock, notes, created_at, updated_at)
            VALUES (%s, 'legacy', '', '件', '', 0, '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING id
        """, [group.id])
        item = Consumable.objects.get(pk=cursor.fetchone()[0])
    assert not item.tracks_batches
    _, txns, _ = paths(item)
    assert api(manager).post(txns, {"kind": "in", "quantity": 1}).status_code == 201


@pytest.mark.django_db(transaction=True)
def test_concurrent_batch_issues_cannot_overdraw(api, manager, student_a, group):
    item = Consumable.objects.create(group=group, name="耦合剂")
    client = api(manager)
    detail, txns, _ = paths(item)
    assert switch(client, item, True).status_code == 200
    assert client.post(txns, {"kind": "in", "quantity": 1, "batch_no": "A"}).status_code == 201
    batch_id = client.get(detail).data["batches"][0]["id"]
    start = Barrier(2, timeout=10)

    def take():
        try:
            own = api(student_a)
            start.wait()
            return own.post(txns, {"kind": "out", "quantity": 1, "batch_id": batch_id}).status_code
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.submit(take), pool.submit(take)
        assert sorted([a.result(timeout=15), b.result(timeout=15)]) == [201, 400]
    assert client.get(detail).data["stock"] == 0
    assert item.txns.filter(kind=StockTxn.Kind.OUT).count() == 1


def test_opening_failure_rolls_back_both_sides_and_mode(api, manager, group, monkeypatch):
    item = Consumable.objects.create(group=group, name="耦合剂")
    client = api(manager)
    detail, txns, _ = paths(item)
    assert client.post(txns, {"kind": "in", "quantity": 3}).status_code == 201
    before = client.get(detail).data

    def unavailable_marker(**fields):
        assert fields["kind"] == StockTxn.Kind.BATCH_MODE
        raise RuntimeError("simulate marker failure after allocation")

    monkeypatch.setattr(StockTxn.objects, "create", unavailable_marker)
    with pytest.raises(RuntimeError, match="simulate marker failure"):
        switch(client, item, True, opening_batch={"batch_no": "rollback"})
    assert client.get(detail).data == before
    assert item.txns.count() == 1
    assert not item.batches.exists()
