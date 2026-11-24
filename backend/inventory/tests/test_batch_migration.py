import pytest
from django.db import connection
from django.db.migrations.exceptions import IrreversibleError
from django.db.migrations.executor import MigrationExecutor

from inventory.models import Consumable, StockTxn

pytestmark = pytest.mark.django_db(transaction=True)
PREVIOUS = ("inventory", "0002_stocktxn_purchase")


def test_unused_migration_can_be_reversed_with_existing_legacy_ledger(manager):
    item = Consumable.objects.create(group=manager.group, name="原有耗材")
    entry = StockTxn.objects.create(consumable=item, handler=manager, kind="in", quantity=10)
    executor = MigrationExecutor(connection)
    leaves = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate([PREVIOUS])
        old = executor.loader.project_state([PREVIOUS]).apps
        assert old.get_model("inventory", "StockTxn").objects.get(pk=entry.pk).quantity == 10
        assert old.get_model("inventory", "Consumable").objects.get(pk=item.pk).name == "原有耗材"
    finally:
        MigrationExecutor(connection).migrate(leaves)
    item.refresh_from_db()
    assert not item.tracks_batches
    entry.refresh_from_db()
    assert entry.quantity == 10 and entry.batch_id is None


def test_used_migration_refuses_reverse_and_preserves_mode_history(api, manager):
    item = Consumable.objects.create(group=manager.group, name="乌龙胶")
    url = f"/api/consumables/{item.pk}/batch-mode/"
    client = api(manager)
    active = client.post(url, {"tracks_batches": True, "stock_version_seen": 0}).data
    assert active["tracks_batches"]
    assert client.post(url, {"tracks_batches": False, "stock_version_seen": active["stock_version"]}).status_code == 200
    leaves = MigrationExecutor(connection).loader.graph.leaf_nodes()
    try:
        with pytest.raises(IrreversibleError, match="不能自动降级"):
            MigrationExecutor(connection).migrate([PREVIOUS])
    finally:  # later migrations were unapplied before the refusal: put them back for the tests that follow
        MigrationExecutor(connection).migrate(leaves)
    # Even a once-enabled then disabled item retains its revision history.
    assert not Consumable.objects.get(pk=item.pk).tracks_batches
    assert list(item.txns.order_by("pk").values_list("kind", "quantity")) == [("batch_mode", 0), ("batch_mode", 0)]
