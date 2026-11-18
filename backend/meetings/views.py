from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from core.files import checked_upload, delete_on_commit, download
from core.history import serialize_history
from core.permissions import IsActiveMember, IsManager, is_manager, scope_group

from .models import ActionItem, AgendaItem, Meeting, MeetingFile
from .serializers import ActionItemSerializer, MeetingFileSerializer, MeetingSerializer


class MeetingViewSet(viewsets.ModelViewSet):
    """Group-wide read; managers create and edit meetings; presenters on the agenda upload their files."""

    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    serializer_class = MeetingSerializer

    def get_permissions(self):
        if self.action in ("create", "partial_update", "destroy"):
            return [IsActiveMember(), IsManager()]
        return [IsActiveMember()]

    def get_queryset(self):
        return scope_group(Meeting.objects.select_related("created_by"), self.request.user).prefetch_related(
            Prefetch("agenda", AgendaItem.objects.select_related("presenter")),
            Prefetch("actions", ActionItem.objects.select_related("owner")),
            Prefetch("files", MeetingFile.objects.select_related("uploaded_by")),
        )

    def perform_create(self, serializer):
        serializer.save(group=self.request.user.group, created_by=self.request.user)

    def perform_destroy(self, meeting):
        with transaction.atomic():
            delete_on_commit([f.file for f in meeting.files.all()])
            meeting.delete()

    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser])
    def files(self, request, pk=None):
        meeting = self.get_object()
        presenting = any(item.presenter_id == request.user.id for item in meeting.agenda.all())
        if not (presenting or is_manager(request.user)):
            raise PermissionDenied("只有议程里的汇报人和管理员可以上传附件")
        uploaded, name = checked_upload(request)
        meeting_file = MeetingFile(meeting=meeting, name=name, size=uploaded.size, uploaded_by=request.user)
        meeting_file.file.save(name, uploaded, save=False)
        try:
            meeting_file.save()
        except Exception:
            meeting_file.file.delete(save=False)
            raise
        return Response(MeetingFileSerializer(meeting_file).data, status=status.HTTP_201_CREATED)

    @action(detail=True)
    def history(self, request, pk=None):
        return Response(serialize_history(self.get_object()))


class MeetingFileViewSet(mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """Download and delete only; uploads go through the meeting."""

    def get_queryset(self):
        return scope_group(MeetingFile.objects.all(), self.request.user, "meeting__group")

    @action(detail=True)
    def file(self, request, pk=None):
        meeting_file = self.get_object()
        return download(meeting_file.file, meeting_file.name)

    def perform_destroy(self, meeting_file):
        if not (meeting_file.uploaded_by_id == self.request.user.id or is_manager(self.request.user)):
            raise PermissionDenied("只有上传人和管理员可以删除附件")
        with transaction.atomic():
            delete_on_commit([meeting_file.file])
            meeting_file.delete()


class DoneSerializer(serializers.Serializer):
    done = serializers.BooleanField()


class ActionItemViewSet(viewsets.GenericViewSet):
    """Only marks an item done or not: the owner or a manager. The rest is edited with the meeting."""

    def get_queryset(self):
        return scope_group(ActionItem.objects.select_related("owner"), self.request.user, "meeting__group")

    @action(detail=True, methods=["post"])
    def done(self, request, pk=None):
        item = self.get_object()
        if not (item.owner_id == request.user.id or is_manager(request.user)):
            raise PermissionDenied("只有负责人和管理员可以修改完成状态")
        data = DoneSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        item.done_at = timezone.now() if data.validated_data["done"] else None
        item.save(update_fields=["done_at"])
        return Response(ActionItemSerializer(item).data)
