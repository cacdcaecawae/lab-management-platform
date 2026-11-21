import secrets

from django.db import transaction
from django.db.models import Q
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.response import Response

from core.permissions import IsManager, scope_group

from .member_serializers import IdsSerializer, MemberCreateSerializer, MemberSerializer, PendingMemberSerializer
from .mixins import ResetPasswordMixin
from .models import User

SIGNUP_ACTIONS = ("pending", "approve", "reject", "signup")


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
            # Managers handle student accounts and their own profile. Advisor, manager and ops accounts are
            # managed by ops in 系统管理: otherwise a manager could take one over (e.g. to pass the advisor's final approval).
            members = members.filter(Q(role=User.Role.STUDENT) | Q(pk=self.request.user.pk), is_superuser=False, is_staff=False)
        if self.action != "list":  # list filters must not turn detail URLs into 404s
            return members
        params = self.request.query_params
        if params.get("role"):
            if params["role"] not in User.Role.values:
                return members.none()
            members = members.filter(role=params["role"])
        if params.get("is_active"):
            members = members.filter(is_active=serializers.BooleanField().to_internal_value(params["is_active"]))
        return members

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
