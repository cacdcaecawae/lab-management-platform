from rest_framework.routers import SimpleRouter

from .notification_views import NotificationViewSet


router = SimpleRouter()
router.register("notifications", NotificationViewSet, basename="notification")
urlpatterns = router.urls
