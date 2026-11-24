# Mounted at /api/ — see docs/api-contract.md for the routes this app owns.
from rest_framework.routers import SimpleRouter

from .views import LoanViewSet, SpecimenViewSet

router = SimpleRouter()
router.register("specimens", SpecimenViewSet, basename="specimen")
router.register("specimen-loans", LoanViewSet, basename="specimen-loan")
urlpatterns = router.urls
