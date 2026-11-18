# Mounted at /api/ — see docs/api-contract.md for the routes this app owns.
from rest_framework.routers import SimpleRouter

from .views import AttachmentViewSet, FundViewSet, PurchaseViewSet, ReimbursementViewSet

router = SimpleRouter()
router.register("funds", FundViewSet, basename="fund")
router.register("purchases", PurchaseViewSet, basename="purchase")
router.register("reimbursements", ReimbursementViewSet, basename="reimbursement")
router.register("attachments", AttachmentViewSet, basename="attachment")
urlpatterns = router.urls
