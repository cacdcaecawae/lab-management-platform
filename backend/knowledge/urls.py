# Mounted at /api/ — see docs/api-contract.md for the routes this app owns.
from rest_framework.routers import SimpleRouter

from .views import DocViewSet

router = SimpleRouter()
router.register("docs", DocViewSet, basename="doc")
urlpatterns = router.urls
