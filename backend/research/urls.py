# Mounted at /api/ — see docs/api-contract.md for the routes this app owns.
from rest_framework.routers import SimpleRouter

from . import views

# SimpleRouter, not DefaultRouter: other apps share the /api/ prefix, so no API root view here.
router = SimpleRouter()
router.register("experiments", views.ExperimentViewSet)
router.register("runs", views.ProcessingRunViewSet)
urlpatterns = router.urls
