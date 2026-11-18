# /api/members/ — owned by Agent A (feat/projects). See docs/api-contract.md.
from rest_framework.routers import SimpleRouter

from .member_views import MemberViewSet

router = SimpleRouter()
router.register("", MemberViewSet, basename="member")
urlpatterns = router.urls
