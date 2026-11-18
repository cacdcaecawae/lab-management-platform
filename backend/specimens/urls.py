# Mounted at /api/ — see docs/api-contract.md for the routes this app owns.
from rest_framework.routers import SimpleRouter

from .views import SpecimenViewSet

router = SimpleRouter()
router.register("specimens", SpecimenViewSet, basename="specimen")
urlpatterns = router.urls
