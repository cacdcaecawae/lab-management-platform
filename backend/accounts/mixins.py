"""View mixins shared by the members page and 系统管理 (system app)."""

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from .member_serializers import PasswordResetSerializer


class ResetPasswordMixin:
    """POST {id}/reset-password/ {password}. The viewset's queryset decides whose password may be reset."""

    @action(detail=True, methods=["post"], url_path="reset-password")
    def reset_password(self, request, pk=None):
        serializer = PasswordResetSerializer(self.get_object(), data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(status=status.HTTP_204_NO_CONTENT)
