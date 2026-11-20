from django.contrib import admin
from django.urls import include, path

from workbench.storage import GroupStorageView, OpsStorageView
from workbench.search import SearchView
from workbench.views import DashboardView

admin.site.site_header = admin.site.site_title = "课题组管理平台 后台"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("accounts.urls")),
    path("api/dashboard/", DashboardView.as_view()),
    path("api/", include("core.notification_urls")),
    path("api/search/", SearchView.as_view(), name="global-search"),
    path("api/members/", include("accounts.member_urls")),
    path("api/system/storage/", OpsStorageView.as_view(), name="ops-storage"),
    path("api/storage-usage/", GroupStorageView.as_view(), name="group-storage-usage"),
    path("api/system/", include("system.urls")),
    path("api/", include("projects.urls")),
    path("api/", include("datasets.urls")),
    path("api/", include("research.urls")),
    path("api/", include("reports.urls")),
    path("api/", include("equipment.urls")),
    path("api/", include("inventory.urls")),
    path("api/", include("procurement.urls")),
    path("api/", include("knowledge.urls")),
    path("api/", include("meetings.urls")),
    path("api/", include("achievements.urls")),
    path("api/", include("specimens.urls")),
]
