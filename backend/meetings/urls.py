# Mounted at /api/ — see docs/api-contract.md for the routes this app owns.
from rest_framework.routers import SimpleRouter

from .views import ActionItemViewSet, MeetingFileViewSet, MeetingViewSet

router = SimpleRouter()
router.register("meetings", MeetingViewSet, basename="meeting")
router.register("meeting-files", MeetingFileViewSet, basename="meeting-file")
router.register("action-items", ActionItemViewSet, basename="action-item")
urlpatterns = router.urls
