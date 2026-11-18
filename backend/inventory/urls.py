# Mounted at /api/ — see docs/api-contract.md for the routes this app owns.
from rest_framework.routers import SimpleRouter

from .views import ConsumableViewSet

router = SimpleRouter()
router.register("consumables", ConsumableViewSet, basename="consumable")
urlpatterns = router.urls
