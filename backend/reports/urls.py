# Mounted at /api/ — see docs/api-contract.md for the routes this app owns.
from rest_framework.routers import SimpleRouter

from .views import WeeklyReportViewSet

router = SimpleRouter()
router.register("reports", WeeklyReportViewSet, basename="report")
urlpatterns = router.urls
