"""系统管理, for the ops account (Django superuser) only. It grants no access to research data: the business
endpoints still answer `no_group` to an ops account."""

import json
import re
import urllib.error
import urllib.request

from django.conf import settings
from django.core.cache import cache
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import mixins, serializers, viewsets
from rest_framework.filters import SearchFilter
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.mixins import ResetPasswordMixin
from accounts.models import ResearchGroup, User
from core import mail
from core.exceptions import Conflict, MailFailed
from core.history import serialize_history
from core.models import SiteSettings
from core.permissions import IsSuperuser

from .serializers import (
    AccountCreateSerializer,
    AccountSerializer,
    MailSettingsSerializer,
    MailTestSerializer,
    SystemGroupSerializer,
)


class MailSettingsView(APIView):
    permission_classes = [IsSuperuser]

    def get(self, request):
        return Response(MailSettingsSerializer(SiteSettings.load()).data)

    def put(self, request):
        serializer = MailSettingsSerializer(SiteSettings.load(), data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class MailHistoryView(APIView):
    permission_classes = [IsSuperuser]

    def get(self, request):
        return Response(serialize_history(SiteSettings.load()))


class MailTestView(APIView):
    """Sends with the saved settings, even while mail is off, so the account can be tried before switching it on."""

    permission_classes = [IsSuperuser]

    def post(self, request):
        data = MailTestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        if not SiteSettings.load().mail_host:
            raise Conflict("请先填写并保存 SMTP 服务器", code="not_configured")
        to = data.validated_data["to"]
        body = "这是课题组管理平台发出的测试邮件。收到这封邮件，说明邮件设置可以正常使用。"
        try:
            mail.send("[课题组管理平台] 测试邮件", body, [to], test=True)
        except Exception as exc:
            raise MailFailed(f"发送失败：{mail.describe(exc)}") from exc
        return Response({"to": to})


RELEASE_CACHE = "system:latest-release"


def parse_version(tag):
    """(major, minor, patch) of a release tag like v1.2.3; None for "local" builds and anything else."""
    match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", tag or "")
    return tuple(map(int, match.groups())) if match else None


def latest_release():
    """The newest GitHub release, cached for 6 hours, or 10 minutes after a failure (the server may not reach GitHub)."""
    release = cache.get(RELEASE_CACHE)
    if release is None:
        release = {"latest": None, "url": "", "error": "", "checked_at": timezone.localtime()}
        request = urllib.request.Request(
            f"https://api.github.com/repos/{settings.UPDATE_REPO}/releases/latest",
            headers={"Accept": "application/vnd.github+json", "User-Agent": "lab-management-platform"},
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                data = json.load(response)
            release.update(latest=data["tag_name"], url=data["html_url"])
        except urllib.error.HTTPError as exc:
            if exc.code != 404:  # 404: nothing has been released yet
                release["error"] = f"GitHub 返回 {exc.code}"
        except (OSError, ValueError, KeyError, TypeError) as exc:
            release["error"] = f"连不上 GitHub：{getattr(exc, 'reason', exc)}"
        cache.set(RELEASE_CACHE, release, 600 if release["error"] else 6 * 3600)
    return release


class VersionView(APIView):
    """The running version and the latest release; updating is scripts/update.sh on the server, not a button."""

    permission_classes = [IsSuperuser]

    def get(self, request):
        release = latest_release()
        current, latest = parse_version(settings.APP_VERSION), parse_version(release["latest"])
        return Response(
            {"current": settings.APP_VERSION, **release, "update_available": bool(current and latest and latest > current)}
        )


class SystemGroupViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """No delete: members point at their group with PROTECT."""

    http_method_names = ["get", "post", "patch", "head", "options"]
    permission_classes = [IsSuperuser]
    serializer_class = SystemGroupSerializer

    def get_queryset(self):
        active = Count("members", filter=Q(members__is_active=True))
        return ResearchGroup.objects.annotate(member_count=active).order_by("id")


class AccountViewSet(ResetPasswordMixin, mixins.ListModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Member accounts of every group. Ops (superuser) accounts are not listed and cannot be changed here."""

    http_method_names = ["get", "post", "patch", "head", "options"]
    permission_classes = [IsSuperuser]
    filter_backends = [SearchFilter]
    search_fields = ["username", "name", "email"]

    def get_serializer_class(self):
        if self.action == "create":
            return AccountCreateSerializer
        return AccountSerializer

    def get_queryset(self):
        accounts = User.objects.filter(is_superuser=False).select_related("group").order_by("group_id", "id")
        if self.action != "list":  # list filters must not turn detail URLs into 404s
            return accounts
        params = self.request.query_params
        if params.get("group"):
            accounts = accounts.filter(group_id=params["group"]) if params["group"].isdigit() else accounts.none()
        if params.get("role"):
            accounts = accounts.filter(role=params["role"]) if params["role"] in User.Role.values else accounts.none()
        if params.get("is_active"):
            accounts = accounts.filter(is_active=serializers.BooleanField().to_internal_value(params["is_active"]))
        return accounts
