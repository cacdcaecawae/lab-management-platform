from django.db import IntegrityError, transaction
from rest_framework import serializers

from accounts.models import User
from accounts.serializers import UserBriefSerializer
from core.exceptions import Conflict
from core.permissions import scope_group

from .models import Project, ProjectLog


class ProjectBriefSerializer(serializers.ModelSerializer):
    """Embedded in other modules' records. See docs/api-contract.md."""

    class Meta:
        model = Project
        fields = ["id", "name"]


class ProjectLogSerializer(serializers.ModelSerializer):
    author = UserBriefSerializer(read_only=True)

    class Meta:
        model = ProjectLog
        fields = ["id", "date", "content", "author", "created_at"]


class GroupMemberField(serializers.PrimaryKeyRelatedField):
    """Accepts only active members of the requesting user's group."""

    def get_queryset(self):
        return scope_group(User.objects.filter(is_active=True), self.context["request"].user)


class AnyGroupMemberField(GroupMemberField):
    """Also former (inactive) members: for records that outlive membership, e.g. a graduate's achievements."""

    def get_queryset(self):
        return scope_group(User.objects.all(), self.context["request"].user)


class GroupProjectField(serializers.PrimaryKeyRelatedField):
    """A project id from the requesting user's research group."""

    def get_queryset(self):
        return scope_group(Project.objects.all(), self.context["request"].user)


class ProjectSerializer(serializers.ModelSerializer):
    leader = UserBriefSerializer(read_only=True)
    members = UserBriefSerializer(many=True, read_only=True)
    leader_id = GroupMemberField(source="leader", write_only=True)
    member_ids = GroupMemberField(source="members", many=True, write_only=True, required=False)
    latest_log = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            "id", "name", "leader", "members", "stage", "status", "description", "latest_log",
            "created_at", "updated_at", "leader_id", "member_ids",
        ]

    def get_latest_log(self, project):
        # ProjectViewSet prefetches `latest_logs`; otherwise (e.g. right after create) query it.
        logs = project.latest_logs if hasattr(project, "latest_logs") else project.logs.all()[:1]
        return ProjectLogSerializer(logs[0]).data if logs else None

    def validate_name(self, value):
        same_name = scope_group(Project.objects.filter(name=value), self.context["request"].user)
        if self.instance:
            same_name = same_name.exclude(pk=self.instance.pk)
        if same_name.exists():
            raise Conflict("本组已有同名项目")
        return value

    def save(self, **kwargs):
        try:
            with transaction.atomic():
                project = super().save(**kwargs)
                project.members.add(project.leader)
        except IntegrityError:  # a concurrent request created the same name after validate_name
            raise Conflict("本组已有同名项目")
        return project
