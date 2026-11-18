"""Data-scope rules. Every view that returns group data MUST build its queryset with
scope_private() or scope_group(); object lookups then 404 for out-of-scope rows.

- Private records (experiments, datasets, runs, weekly reports): owner + supervisors
  (manager / advisor) of the owner's research group.
- Group records (projects, member list): everyone in the same research group.
"""

from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied


def is_supervisor(user):
    return bool(user and user.is_authenticated and user.group_id and user.is_supervisor)


def is_manager(user):
    """Managers (not advisors) maintain the group's equipment and consumables."""
    return bool(user and user.is_authenticated and user.group_id and user.role == "manager")


def scope_private(queryset, user, owner_field="owner"):
    if not (user and user.is_authenticated and user.group_id):
        return queryset.none()
    if user.is_supervisor:
        return queryset.filter(**{f"{owner_field}__group_id": user.group_id})
    return queryset.filter(**{owner_field: user})


def scope_group(queryset, user, group_field="group"):
    if not (user and user.is_authenticated and user.group_id):
        return queryset.none()
    return queryset.filter(**{group_field: user.group_id})


class IsActiveMember(permissions.BasePermission):
    """Default for all API views: logged in, and the initial password has been changed."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.must_change_password:
            raise PermissionDenied(detail="请先修改初始密码", code="password_change_required")
        if not user.group_id:
            raise PermissionDenied(detail="账号未分配课题组，请联系管理员", code="no_group")
        return True


class IsManager(permissions.BasePermission):
    message = "仅管理员可操作"

    def has_permission(self, request, view):
        return is_manager(request.user)


class IsSuperuser(permissions.BasePermission):
    """系统管理: the ops account (a Django superuser, usually without a group). Replaces IsActiveMember there."""

    message = "仅运维账号可操作"

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated and user.is_superuser):
            return False
        if user.must_change_password:
            raise PermissionDenied(detail="请先修改初始密码", code="password_change_required")
        return True


class IsSupervisor(permissions.BasePermission):
    message = "仅管理员或导师可操作"

    def has_permission(self, request, view):
        return is_supervisor(request.user)


class IsOwnerOrReadOnly(permissions.BasePermission):
    """Reads are governed by the scoped queryset; writes only by the record owner."""

    message = "只能修改自己的记录"

    def has_object_permission(self, request, view, obj):
        return request.method in permissions.SAFE_METHODS or obj.owner_id == request.user.id
