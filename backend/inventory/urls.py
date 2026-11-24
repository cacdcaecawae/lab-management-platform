# Mounted at /api/ — see docs/api-contract.md for the routes this app owns.
from rest_framework.routers import SimpleRouter

from .views import ConsumableViewSet, StockTxnViewSet

router = SimpleRouter()
router.register("consumables", ConsumableViewSet, basename="consumable")
router.register("stock-txns", StockTxnViewSet, basename="stock-txn")
urlpatterns = router.urls
