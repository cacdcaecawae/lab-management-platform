# /api/system/ — 系统管理, ops account only. See docs/api-contract.md.
from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views
from .storage import StorageView

router = SimpleRouter()
router.register("groups", views.SystemGroupViewSet, basename="system-group")
router.register("accounts", views.AccountViewSet, basename="system-account")

urlpatterns = [
    path("mail/", views.MailSettingsView.as_view()),
    path("mail/history/", views.MailHistoryView.as_view()),
    path("mail/test/", views.MailTestView.as_view()),
    path("storage/", StorageView.as_view()),
    path("version/", views.VersionView.as_view()),
    *router.urls,
]
