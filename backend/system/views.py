"""系统管理, for the ops account (Django superuser) only. It grants no access to research data: the business
endpoints still answer `no_group` to an ops account."""

import json
import re
import time
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
from core.params import plain_int
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
        body = "这是 Phase 发出的测试邮件。收到这封邮件，说明邮件设置可以正常使用。"
        try:
            mail.send("[Phase] 测试邮件", body, [to], test=True)
        except Exception as exc:
            raise MailFailed(f"发送失败：{mail.describe(exc)}") from exc
        return Response({"to": to})


RELEASE_CACHE = "system:latest-release"


def parse_version(tag):
    """(major, minor, patch) of a release tag like v1.2.3; None for "local" builds and anything else."""
    match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", tag or "")
    return tuple(map(int, match.groups())) if match else None


def latest_release(refresh=False):
    """The newest GitHub release, cached for an hour, or 10 minutes after a failure (the server may not reach GitHub)."""
    release = None if refresh else cache.get(RELEASE_CACHE)
    cached, running = parse_version(release and release["latest"]), parse_version(settings.APP_VERSION)
    if cached and running and cached < running:  # checked before this release was installed
        release = None
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
        cache.set(RELEASE_CACHE, release, 600 if release["error"] else 3600)
    return release


def agent_running():
    """scripts/update-agent.sh marks itself alive every 30 seconds; cron restarts it within a minute after an update."""
    try:
        return time.time() - (settings.UPDATE_DIR / "status" / "agent").stat().st_mtime < 90
    except OSError:
        return False


class VersionView(APIView):
    """The running version and the latest release; ?refresh=1 asks GitHub again."""

    permission_classes = [IsSuperuser]

    def get(self, request):
        release = latest_release(refresh=request.query_params.get("refresh") == "1")
        current, latest = parse_version(settings.APP_VERSION), parse_version(release["latest"])
        update_available = bool(current and latest and latest > current)
        return Response({"current": settings.APP_VERSION, **release, "update_available": update_available, "agent": agent_running()})


class UpdateView(APIView):
    """立即更新: asks scripts/update-agent.sh on the server to run update.sh. The request is an empty file named after the
    release, which must be the newest one and newer than this; the agent and update.sh check it again."""

    permission_classes = [IsSuperuser]

    def post(self, request):
        target = request.data.get("target")
        release = latest_release()
        current, latest = parse_version(settings.APP_VERSION), parse_version(release["latest"])
        if not (current and latest and latest > current) or target != release["latest"]:
            raise Conflict("只能更新到最新的正式版本，请刷新页面后再试", code="not_latest")
        if not agent_running():
            raise Conflict("服务器上的更新助手没有运行，请在服务器上运行更新命令", code="no_agent")
        try:
            (settings.UPDATE_DIR / "request" / target).open("x").close()
        except FileExistsError:
            raise Conflict("已经在更新了", code="updating") from None
        return Response({"target": target, "requested_at": time.time()}, status=202)


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
            accounts = accounts.filter(group_id=params["group"]) if plain_int(params["group"]) else accounts.none()
        if params.get("role"):
            accounts = accounts.filter(role=params["role"]) if params["role"] in User.Role.values else accounts.none()
        if params.get("flag"):  # 管理员 / 终审人, as on the member list
            accounts = accounts.filter(**{f"is_{params['flag']}": True}) if params["flag"] in ("manager", "approver") else accounts.none()
        if params.get("is_active"):
            accounts = accounts.filter(is_active=serializers.BooleanField().to_internal_value(params["is_active"]))
        return accounts
