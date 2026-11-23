import secrets

from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone
from django.utils.http import content_disposition_header
from openpyxl import Workbook
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import SearchFilter
from rest_framework.response import Response

from core.export import xlsx_bytes
from core.params import plain_int
from core.permissions import IsApprover, IsManager, is_supervisor, scope_group

from .member_serializers import STATUSES, IdsSerializer, MemberCreateSerializer, MemberSerializer, PendingMemberSerializer
from .mixins import ResetPasswordMixin
from .models import User

SIGNUP_ACTIONS = ("pending", "approve", "reject", "signup")
STATUS_LOOKUPS = {
    "active": {"is_active": True}, "graduated": {"is_active": False, "graduated": True},
    "disabled": {"is_active": False, "graduated": False},
}
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class MemberViewSet(
    ResetPasswordMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """No delete: members leave the group with is_active=false."""

    http_method_names = ["get", "post", "patch", "head", "options"]
    serializer_class = MemberSerializer
    filter_backends = [SearchFilter]

    @property
    def search_fields(self):
        # Students never see usernames, so they must not be able to probe them through search either.
        if self.request.user.is_supervisor:
            return ["name", "username", "research_direction"]
        return ["name", "research_direction"]

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "reset_password", *SIGNUP_ACTIONS):
            return [*super().get_permissions(), IsManager()]
        if self.action == "manager":
            return [*super().get_permissions(), IsApprover()]
        return super().get_permissions()

    def get_serializer_class(self):
        if self.action == "create":
            return MemberCreateSerializer
        return MemberSerializer

    def get_queryset(self):
        # Applicants are not members yet: only the approval actions see them.
        pending = self.action in SIGNUP_ACTIONS
        members = scope_group(User.objects.filter(pending=pending).order_by("id"), self.request.user)
        if self.action in ("update", "partial_update", "reset_password"):
            # Managers handle plain student accounts and their own profile. Advisors, other managers, approvers and ops
            # are managed in 系统管理: otherwise a manager could take one over (e.g. to pass the final approval).
            plain = Q(role=User.Role.STUDENT, is_manager=False, is_approver=False)
            members = members.filter(plain | Q(pk=self.request.user.pk), is_superuser=False, is_staff=False)
        if self.action == "manager":
            members = members.filter(is_superuser=False, is_staff=False)  # any member's 管理员 tag, never ops
        if self.action not in ("list", "export"):  # list filters must not turn detail URLs into 404s
            return members
        params = self.request.query_params
        choices = {"role": User.Role.values, "identity": User.Identity.values}
        for name, values in choices.items():
            if params.get(name):
                members = members.filter(**{name: params[name]}) if params[name] in values else members.none()
        if params.get("flag"):  # 管理员 / 终审人
            members = members.filter(**{f"is_{params['flag']}": True}) if params["flag"] in ("manager", "approver") else members.none()
        if params.get("tag"):
            members = members.filter(tags__contains=[params["tag"]]) if "\x00" not in params["tag"] else members.none()
        if params.get("year"):
            year = plain_int(params["year"], 4)
            members = members.filter(enrollment_year=year) if year else members.none()
        if params.get("status"):
            lookups = STATUS_LOOKUPS.get(params["status"])
            members = members.filter(**lookups) if lookups else members.none()
        if params.get("is_active"):
            members = members.filter(is_active=serializers.BooleanField().to_internal_value(params["is_active"]))
        return members

    @action(detail=True, methods=["post"])
    def manager(self, request, pk=None):
        """The 终审人 gives the 管理员 tag to an account of the group, or takes it back."""
        on = serializers.BooleanField().run_validation(request.data.get("is_manager"))
        member = self.get_object()
        member.is_manager = on
        member.save(update_fields=["is_manager"])
        return Response(MemberSerializer(member, context=self.get_serializer_context()).data)

    @action(detail=False)
    def export(self, request):
        """花名册: the filtered list as .xlsx. It holds login names and contact details: advisors and managers only."""
        if not is_supervisor(request.user):
            raise PermissionDenied("仅导师或管理员可以导出花名册")
        book = Workbook()
        sheet = book.active
        sheet.title = "花名册"
        sheet.append(["姓名", "学号 / 工号", "基础角色", "管理员", "终审人", "身份", "入学年份", "状态", "词条", "邮箱", "电话", "研究方向"])
        for m in self.filter_queryset(self.get_queryset()):
            sheet.append([
                m.name, m.username, m.get_role_display(), "是" if m.is_manager else "", "是" if m.is_approver else "",
                m.get_identity_display(), f"{m.enrollment_year}级" if m.enrollment_year else "", STATUSES[m.member_status],
                "、".join(m.tags), m.email, m.phone, m.research_direction,
            ])
        response = HttpResponse(xlsx_bytes(book), content_type=XLSX)
        stamp = timezone.localdate().strftime("%Y%m%d")
        response["Content-Disposition"] = content_disposition_header(as_attachment=True, filename=f"花名册-{stamp}.xlsx")
        return response

    @action(detail=False)
    def pending(self, request):
        """Applications waiting for this group's managers (at most PENDING_LIMIT, so not paged)."""
        return Response(PendingMemberSerializer(self.get_queryset(), many=True).data)

    def chosen(self, request):
        ids = IdsSerializer(data=request.data)
        ids.is_valid(raise_exception=True)
        return self.get_queryset().filter(pk__in=ids.validated_data["ids"])  # IDs outside the group's applicants: ignored

    @action(detail=False, methods=["post"])
    def approve(self, request):
        return Response({"count": self.chosen(request).update(is_active=True, pending=False)})

    @action(detail=False, methods=["post"])
    def reject(self, request):
        with transaction.atomic():
            # Locked before deleting: an approval by another manager lands first (the row no longer matches) or waits.
            ids = list(self.chosen(request).select_for_update().values_list("pk", flat=True))
            # Never activated, so there is nothing of theirs to keep; the student number is free to apply again.
            User.objects.filter(pk__in=ids).delete()
        return Response({"count": len(ids)})

    @action(detail=False, methods=["get", "post"])
    def signup(self, request):
        """The group's registration link: GET reads it; POST {open: true} makes a new one, {open: false} turns it off."""
        group = request.user.group
        if request.method == "POST":
            group.signup_code = secrets.token_urlsafe(9) if serializers.BooleanField().run_validation(request.data.get("open")) else ""
            group.save(update_fields=["signup_code"])
        return Response({"code": group.signup_code})
