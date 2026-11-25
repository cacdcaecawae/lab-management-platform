from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.utils import timezone
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import SearchFilter
from rest_framework.generics import get_object_or_404
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from accounts.models import User
from core.files import checked_upload, delete_on_commit, download
from core.params import plain_int
from core.permissions import IsActiveMember, is_supervisor, scope_group

from .task_views import milestones_endpoint, tasks_endpoint
from .models import Project, ProjectFile, ProjectLog, Task
from .serializers import ProjectFileSerializer, ProjectLogSerializer, ProjectSerializer

# Writes a project's current members may make besides the leader and supervisors, and the refusal for the rest.
MEMBER_ACTIONS = {"logs": "仅本项目成员、管理员或导师可以写进展", "files": "仅本项目成员、管理员或导师可以上传文件"}


class ProjectPermission(permissions.BasePermission):
    """Create: supervisors. Edit: supervisors or the project leader. Add a progress log or a project file: also the
    project's current members. Read: the whole group."""

    message = "仅管理员、导师或项目负责人可操作"

    def has_permission(self, request, view):
        return view.action != "create" or is_supervisor(request.user)

    def has_object_permission(self, request, view, project):
        user = request.user
        if request.method in permissions.SAFE_METHODS or is_supervisor(user) or project.leader_id == user.id:
            return True
        if view.action in MEMBER_ACTIONS and project.members.filter(pk=user.pk).exists():
            return True
        self.message = MEMBER_ACTIONS.get(view.action, ProjectPermission.message)
        return False


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
        # open tasks past their due date, counted as the workbench does
        late = Q(tasks__due_date__lt=timezone.localdate()) & ~Q(tasks__status=Task.Status.DONE)
        projects = (
            scope_group(Project.objects.all(), user).select_related("leader").prefetch_related(
                Prefetch("members", queryset=User.objects.order_by("id")),
                Prefetch("logs", queryset=ProjectLog.objects.select_related("author")[:1], to_attr="latest_logs"),
            )
            .annotate(overdue_tasks=Count("tasks", filter=late, distinct=True))  # distinct: ?mine=1 joins the members
            .order_by("-updated_at", "-id")  # explicit: Django drops Meta.ordering on aggregated (GROUP BY) querysets
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
        if leader := params.get("leader"):
            projects = projects.filter(leader_id=plain_int(leader)) if plain_int(leader) else projects.none()
        if params.get("overdue") == "1":
            projects = projects.filter(overdue_tasks__gt=0)
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

    @action(detail=True, methods=["get", "post"], parser_classes=[MultiPartParser])
    def files(self, request, pk=None):
        project = self.get_object()
        if request.method == "GET":
            return Response(ProjectFileSerializer(project.files.select_related("uploaded_by"), many=True).data)
        uploaded, name = checked_upload(request)
        project_file = ProjectFile(project=project, name=name, size=uploaded.size, uploaded_by=request.user)
        project_file.file.save(name, uploaded, save=False)
        try:
            project_file.save()  # projects are never deleted, so no lock as for a meeting's files
        except Exception:
            project_file.file.delete(save=False)
            raise
        return Response(ProjectFileSerializer(project_file).data, status=status.HTTP_201_CREATED)

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


class LogPermission(permissions.BasePermission):
    message = "仅记录人、项目负责人、管理员或导师可以修改或删除进展"

    def has_object_permission(self, request, view, log):
        user = request.user
        return log.author_id == user.id or log.project.leader_id == user.id or is_supervisor(user)


class ProjectLogViewSet(mixins.UpdateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """Changing or deleting a progress log: whoever wrote it, the project leader, advisors and managers.
    Adding and listing go through the project."""

    http_method_names = ["patch", "delete", "options"]
    serializer_class = ProjectLogSerializer
    permission_classes = [IsActiveMember, LogPermission]

    def get_queryset(self):
        return scope_group(ProjectLog.objects.select_related("author", "project"), self.request.user, "project__group")


class ProjectFileViewSet(mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """Download and delete only; uploads go through the project."""

    def get_queryset(self):
        return scope_group(ProjectFile.objects.select_related("project"), self.request.user, "project__group")

    @action(detail=True)
    def file(self, request, pk=None):
        project_file = self.get_object()
        return download(project_file.file, project_file.name)

    def perform_destroy(self, project_file):
        user = self.request.user
        if not (project_file.uploaded_by_id == user.id or project_file.project.leader_id == user.id or is_supervisor(user)):
            raise PermissionDenied("只有上传人、项目负责人、导师和管理员可以删除文件")
        with transaction.atomic():
            delete_on_commit([project_file.file])
            project_file.delete()
