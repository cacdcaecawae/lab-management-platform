# Mounted at /api/ — see docs/api-contract.md for the routes this app owns.
from rest_framework.routers import SimpleRouter

from .views import AchievementViewSet

router = SimpleRouter()
router.register("achievements", AchievementViewSet, basename="achievement")
urlpatterns = router.urls
