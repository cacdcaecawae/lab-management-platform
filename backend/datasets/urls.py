# Mounted at /api/ — see docs/api-contract.md for the routes this app owns.
from rest_framework.routers import SimpleRouter

from .views import DataFileViewSet, DatasetViewSet

router = SimpleRouter()
router.register("datasets", DatasetViewSet, basename="dataset")
router.register("files", DataFileViewSet, basename="datafile")
urlpatterns = router.urls
