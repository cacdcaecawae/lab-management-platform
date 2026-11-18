# Mounted at /api/ — see docs/api-contract.md for the routes this app owns.
from rest_framework.routers import SimpleRouter

from .views import ProjectViewSet

router = SimpleRouter()
router.register("projects", ProjectViewSet, basename="project")
urlpatterns = router.urls
