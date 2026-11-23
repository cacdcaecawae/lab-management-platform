from django.db import transaction
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from core.permissions import IsActiveMember, scope_group

from .models import Milestone, Project, Task, TaskChange
from .queries import board_tasks
from .task_board import (
    MilestoneSerializer, TaskSerializer, board_manager, board_milestones,
    record_change, task_editor, task_snapshot,
)


def task_list(project):
    return board_tasks(project.tasks.all()).prefetch_related(
        Prefetch("history", queryset=TaskChange.objects.all()[:20], to_attr="recent_changes")
    )


def tasks_endpoint(view, request, project):
    if request.method == "POST":
        if not task_editor(request.user, project):
            raise PermissionDenied("仅本项目成员或负责人、管理员、导师可操作")
        serializer = TaskSerializer(data=request.data, context={"request": request, "project": project})
        serializer.is_valid(raise_exception=True)
        task = serializer.save(project=project, created_by=request.user)
        record_change(task, request.user, {}, task_snapshot(task))
        return Response(TaskSerializer(task_list(project).get(pk=task.pk)).data, status=status.HTTP_201_CREATED)
    queryset = task_list(project)
    params = request.query_params
    if "status" in params:
        if params["status"] not in Task.Status.values:
            raise ValidationError({"status": "无效任务状态"})
        queryset = queryset.filter(status=params["status"])
    for name in ("assignee", "milestone"):
        if name in params:
            try:
                value = int(params[name])
                if not 1 <= value <= 2**63 - 1:
                    raise ValueError
            except ValueError:
                raise ValidationError({name: "请输入有效编号"}) from None
            queryset = queryset.filter(**{f"{name}_id": value})
    return view.get_paginated_response(TaskSerializer(view.paginate_queryset(queryset), many=True).data)


def milestones_endpoint(view, request, project):
    queryset = board_milestones(project.milestones.all())
    if request.method == "POST":
        if not board_manager(request.user, project):
            raise PermissionDenied("仅项目负责人、管理员、导师可操作")
        serializer = MilestoneSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        milestone = serializer.save(project=project)
        return Response(MilestoneSerializer(queryset.get(pk=milestone.pk)).data, status=status.HTTP_201_CREATED)
    return view.get_paginated_response(MilestoneSerializer(view.paginate_queryset(queryset), many=True).data)


class BoardDetailViewSet(mixins.UpdateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsActiveMember]
    http_method_names = ["patch", "delete", "options"]

    def get_queryset(self):
        return scope_group(self.model.objects.all(), self.request.user, "project__group_id")

    def lock_object(self):
        obj = self.get_object()
        project = get_object_or_404(scope_group(Project.objects.all(), self.request.user).select_for_update(), pk=obj.project_id)
        return project, get_object_or_404(self.get_queryset(), pk=obj.pk)


class TaskViewSet(BoardDetailViewSet):
    serializer_class = TaskSerializer
    model = Task

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        project, task = self.lock_object()
        if not task_editor(request.user, project):
            raise PermissionDenied("仅本项目成员或负责人、管理员、导师可操作")
        serializer = self.get_serializer(task, data=request.data, partial=True,
                                         context={"request": request, "project": project})
        serializer.is_valid(raise_exception=True)
        before = task_snapshot(task)
        task = serializer.save()
        record_change(task, request.user, before, task_snapshot(task))
        return Response(TaskSerializer(task_list(project).get(pk=task.pk)).data)

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        project, task = self.lock_object()
        if task.created_by_id != request.user.pk and not board_manager(request.user, project):
            raise PermissionDenied("仅任务创建人、项目负责人、管理员、导师可删除")
        task.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MilestoneViewSet(BoardDetailViewSet):
    serializer_class = MilestoneSerializer
    model = Milestone

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        project, milestone = self.lock_object()
        if not board_manager(request.user, project):
            raise PermissionDenied("仅项目负责人、管理员、导师可操作")
        serializer = self.get_serializer(milestone, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(self.get_serializer(board_milestones(project.milestones.all()).get(pk=milestone.pk)).data)

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        project, milestone = self.lock_object()
        if not board_manager(request.user, project):
            raise PermissionDenied("仅项目负责人、管理员、导师可操作")
        TaskChange.objects.bulk_create([
            TaskChange(task_id=task_id, actor_name=request.user.display_name,
                       changes={"milestone": {"before": milestone.title, "after": None}})
            for task_id in milestone.tasks.values_list("pk", flat=True)
        ])
        milestone.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
