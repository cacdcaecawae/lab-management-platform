"""Project board permissions, queries and serializers."""

from django.db.models import Count, Exists, F, OuterRef, Q
from django.utils import timezone
from rest_framework import serializers

from accounts.models import User
from core.permissions import is_supervisor

from .models import Milestone, Project, Task
from .serializers import GroupMemberField, ProjectBriefSerializer


def board_manager(user, project):
    return is_supervisor(user) or project.leader_id == user.id


def eligible_members(project):
    return User.objects.filter(group_id=project.group_id, is_active=True).filter(Q(pk=project.leader_id) | Q(projects=project)).distinct()


def task_editor(user, project):
    return board_manager(user, project) or eligible_members(project).filter(pk=user.pk).exists()


def board_tasks(queryset):
    member = Project.members.through.objects.filter(project_id=OuterRef("project_id"), user_id=OuterRef("assignee_id"))
    return queryset.annotate(
        assignee_current=(Exists(member) | Q(assignee_id=F("project__leader_id")))
        & Q(assignee__is_active=True, assignee__group_id=F("project__group_id")),
    ).select_related("milestone").order_by(F("due_date").asc(nulls_last=True), "id")


def board_milestones(queryset):
    return queryset.annotate(
        task_total=Count("tasks"),
        task_done=Count("tasks", filter=Q(tasks__status=Task.Status.DONE)),
    ).order_by(F("due_date").asc(nulls_last=True), "id")


def task_snapshot(task):
    return {
        "title": task.title, "description": task.description, "status": task.status,
        "milestone": task.milestone_id, "assignee": task.assignee_id,
        "due_date": task.due_date.isoformat() if task.due_date else None,
    }


def record_change(task, user, before, after):
    changes = {key: {"before": before.get(key), "after": value} for key, value in after.items() if key not in before or before[key] != value}
    if changes:
        task.history.create(actor_name=user.name, changes=changes)


class TaskAssigneeField(GroupMemberField):
    def get_queryset(self):
        # Board writes are atomic and lock the project first. Lock the incoming user
        # too, so deactivation/group transfer cannot interleave with assignment.
        return super().get_queryset().select_for_update()


class TaskSerializer(serializers.ModelSerializer):
    assignee = serializers.SerializerMethodField()
    assignee_id = TaskAssigneeField(source="assignee", required=False, allow_null=True, write_only=True)
    milestone_id = serializers.IntegerField(min_value=1, required=False, allow_null=True, write_only=True)
    milestone = serializers.SerializerMethodField()
    history = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = [
            "id", "title", "description", "assignee", "assignee_id", "status", "milestone", "milestone_id",
            "due_date", "created_by", "created_at", "updated_at", "history",
        ]
        read_only_fields = ["created_by", "created_at", "updated_at"]

    def get_assignee(self, task):
        if task.assignee_id is not None:
            return {"id": task.assignee_id, "name": task.assignee_name, "current": task.assignee_current}
        return None

    def get_milestone(self, task):
        return {"id": task.milestone_id, "title": task.milestone.title} if task.milestone_id else None

    def get_history(self, task):
        prefetched = getattr(task, "recent_changes", None)
        entries = prefetched if prefetched is not None else task.history.all()[:20]
        return [{"actor": entry.actor_name, "changes": entry.changes, "created_at": entry.created_at} for entry in entries]

    def validate(self, attrs):
        project = self.context["project"]
        assignee = attrs.get("assignee")
        if assignee and not eligible_members(project).filter(pk=assignee.pk).exists():
            raise serializers.ValidationError({"assignee_id": "请选择本项目在职成员"})
        milestone = attrs.get("milestone_id")
        if milestone and not project.milestones.filter(pk=milestone).exists():
            raise serializers.ValidationError({"milestone_id": "请选择本项目里程碑"})
        if "assignee" in attrs:
            attrs["assignee_name"] = assignee.name if assignee else ""
        return attrs


class MilestoneSerializer(serializers.ModelSerializer):
    done = serializers.BooleanField(required=False, write_only=True)
    task_total = serializers.IntegerField(read_only=True)
    task_done = serializers.IntegerField(read_only=True)

    class Meta:
        model = Milestone
        fields = ["id", "title", "due_date", "done", "done_at", "created_at", "task_total", "task_done"]
        read_only_fields = ["done_at", "created_at"]

    def validate(self, attrs):
        if "done" in attrs:
            done = attrs.pop("done")
            attrs["done_at"] = (getattr(self.instance, "done_at", None) or timezone.now()) if done else None
        return attrs


class WorkbenchTaskSerializer(serializers.ModelSerializer):
    project = ProjectBriefSerializer(read_only=True)

    class Meta:
        model = Task
        fields = ["id", "title", "due_date", "status", "project"]
