from django.db.models import Q
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.response import Response

from core.permissions import IsManager, scope_group

from .member_serializers import MemberCreateSerializer, MemberSerializer, PasswordResetSerializer
from .models import User


class ResetPasswordMixin:
    """POST {id}/reset-password/ {password}. The viewset's queryset decides whose password may be reset."""

    @action(detail=True, methods=["post"], url_path="reset-password")
    def reset_password(self, request, pk=None):
        serializer = PasswordResetSerializer(self.get_object(), data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


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
        if self.action in ("create", "update", "partial_update", "reset_password"):
            return [*super().get_permissions(), IsManager()]
        return super().get_permissions()

    def get_serializer_class(self):
        if self.action == "create":
            return MemberCreateSerializer
        return MemberSerializer

    def get_queryset(self):
        members = scope_group(User.objects.order_by("id"), self.request.user)
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
