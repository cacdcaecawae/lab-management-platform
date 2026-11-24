"""Data-scope rules. Every view that returns group data MUST build its queryset with
scope_private(), scope_finance() or scope_group(); object lookups then 404 for out-of-scope rows.

- Research records (experiments, datasets, runs, weekly reports): the owner + the advisors of the owner's group.
- Purchases and reimbursements: the owner + the group's managers and approvers (who review and process them).
- Group records (projects, member list, equipment...): everyone in the same research group.

Who may do what: the base role (student / advisor) and two tags (管理员 is_manager, 终审人 is_approver), see
.agents/notes/implemented/architecture/2026-11-23-roles-and-identity.md.
"""

from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied


def member(user):
    return bool(user and user.is_authenticated and user.group_id)


def is_advisor(user):
    """Advisors see the group's research records and review them (experiment returns, weekly report feedback)."""
    return member(user) and user.role == "advisor"


def is_manager(user):
    """The 管理员 tag, on any base role: equipment, specimens, consumables, meetings, funds, members, initial reviews."""
    return member(user) and user.is_manager


def is_approver(user):
    """The 终审人 tag: the final review of purchases, and the 管理员 tag of the group's accounts."""
    return member(user) and user.is_approver


def is_supervisor(user):
    """Advisor or manager: new projects and their leaders, blind defect sizes, usage and storage statistics."""
    return member(user) and (user.role == "advisor" or user.is_manager)


def is_finance(user):
    """Managers and approvers see the group's purchases and reimbursements."""
    return member(user) and (user.is_manager or user.is_approver)


def scope_private(queryset, user, owner_field="owner"):
    """Research records: the owner's own, or the whole group's for an advisor. A student with the 管理员 tag runs the
    group's affairs but does not see other students' records."""
    if not member(user):
        return queryset.none()
    if user.role == "advisor":
        return queryset.filter(**{f"{owner_field}__group_id": user.group_id})
    return queryset.filter(**{owner_field: user})


def scope_finance(queryset, user, owner_field="owner"):
    """Purchases and reimbursements: the owner's own, or the whole group's for a manager or an approver."""
    if not member(user):
        return queryset.none()
    if user.is_manager or user.is_approver:
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


class IsAdvisor(permissions.BasePermission):
    message = "仅导师可操作"

    def has_permission(self, request, view):
        return is_advisor(request.user)


class IsApprover(permissions.BasePermission):
    message = "仅终审人可操作"

    def has_permission(self, request, view):
        return is_approver(request.user)


class IsFinance(permissions.BasePermission):
    message = "仅管理员或终审人可操作"

    def has_permission(self, request, view):
        return is_finance(request.user)


class IsOwnerOrReadOnly(permissions.BasePermission):
    """Reads are governed by the scoped queryset; writes only by the record owner."""

    message = "只能修改自己的记录"

    def has_object_permission(self, request, view, obj):
        return request.method in permissions.SAFE_METHODS or obj.owner_id == request.user.id
