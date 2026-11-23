from django.db import transaction
from django.db.models import Prefetch, Q
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import SearchFilter
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from accounts.models import User
from core.permissions import IsActiveMember, is_supervisor, scope_group

from .task_views import milestones_endpoint, tasks_endpoint
from .models import Project, ProjectLog
from .serializers import ProjectLogSerializer, ProjectSerializer


class ProjectPermission(permissions.BasePermission):
    """Create: supervisors. Edit and add logs: supervisors or the project leader. Read: the whole group."""

    message = "仅管理员、导师或项目负责人可操作"

    def has_permission(self, request, view):
        return view.action != "create" or is_supervisor(request.user)

    def has_object_permission(self, request, view, project):
        if request.method in permissions.SAFE_METHODS:
            return True
        return is_supervisor(request.user) or project.leader_id == request.user.id


class ProjectViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """No delete: projects end with status=closed."""

    http_method_names = ["get", "post", "patch", "head", "options"]
    serializer_class = ProjectSerializer
    permission_classes = [IsActiveMember, ProjectPermission]
    filter_backends = [SearchFilter]
    search_fields = ["name"]

    def get_queryset(self):
        user = self.request.user
        projects = scope_group(Project.objects.all(), user).select_related("leader").prefetch_related(
            Prefetch("members", queryset=User.objects.order_by("id")),
            Prefetch("logs", queryset=ProjectLog.objects.select_related("author")[:1], to_attr="latest_logs"),
        )
        if self.action != "list":  # list filters must not turn detail URLs into 404s
            return projects
        params = self.request.query_params
        if params.get("status"):
            if params["status"] not in Project.Status.values:
                return projects.none()
            projects = projects.filter(status=params["status"])
        if params.get("mine") == "1":
            projects = projects.filter(Q(leader=user) | Q(members=user)).distinct()
        return projects

    def perform_create(self, serializer):
        serializer.save(group=self.request.user.group)

    def perform_update(self, serializer):
        new_leader = serializer.validated_data.get("leader")
        if new_leader and new_leader != serializer.instance.leader and not is_supervisor(self.request.user):
            raise PermissionDenied("只有管理员或导师可以更换负责人")
        serializer.save()

    @action(detail=True, methods=["get", "post"], serializer_class=ProjectLogSerializer)
    def logs(self, request, pk=None):
        project = self.get_object()
        if request.method == "POST":
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save(project=project, author=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        page = self.paginate_queryset(project.logs.select_related("author"))
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    def board_project(self):
        projects = scope_group(Project.objects.all(), self.request.user)
        if self.request.method == "POST":
            projects = projects.select_for_update()
        return get_object_or_404(projects, pk=self.kwargs["pk"])

    @action(detail=True, methods=["get", "post"])
    @transaction.atomic
    def tasks(self, request, pk=None):
        return tasks_endpoint(self, request, self.board_project())

    @action(detail=True, methods=["get", "post"])
    @transaction.atomic
    def milestones(self, request, pk=None):
        return milestones_endpoint(self, request, self.board_project())
