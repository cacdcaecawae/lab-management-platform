# Mounted at /api/ — see docs/api-contract.md for the routes this app owns.
from rest_framework.routers import SimpleRouter

from .views import BookingViewSet, EquipmentViewSet

router = SimpleRouter()
router.register("equipment", EquipmentViewSet, basename="equipment")
router.register("bookings", BookingViewSet, basename="booking")
urlpatterns = router.urls
