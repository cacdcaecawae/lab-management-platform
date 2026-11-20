from django.db.models import Exists, F, OuterRef, Q

from .models import Project


def board_tasks(queryset):
    member = Project.members.through.objects.filter(project_id=OuterRef("project_id"), user_id=OuterRef("assignee_id"))
    return queryset.annotate(
        assignee_current=(Exists(member) | Q(assignee_id=F("project__leader_id")))
        & Q(assignee__is_active=True, assignee__group_id=F("project__group_id")),
    ).select_related("milestone").order_by(F("due_date").asc(nulls_last=True), "id")
