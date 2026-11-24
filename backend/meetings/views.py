from django.db import transaction
from django.db.models import F, Prefetch
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from core.files import checked_upload, delete_on_commit, download
from core.filters import Search
from core.history import serialize_history
from core.params import plain_int
from core.permissions import IsActiveMember, IsManager, IsSupervisor, is_manager, is_supervisor, scope_group

from .models import ActionItem, AgendaItem, Meeting, MeetingFile
from .serializers import ActionItemSerializer, MeetingFileSerializer, MeetingSerializer, MyActionItemSerializer


class MeetingViewSet(viewsets.ModelViewSet):
    """Group-wide read; advisors and managers create and edit meetings, only managers delete them; presenters on the
    agenda upload their files."""

    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    serializer_class = MeetingSerializer
    filter_backends = [Search]
    search_fields = ["title", "minutes", "agenda__topic", "agenda__presenter__name"]

    def get_permissions(self):
        if self.action == "destroy":
            return [IsActiveMember(), IsManager()]
        if self.action in ("create", "partial_update"):
            return [IsActiveMember(), IsSupervisor()]
        return [IsActiveMember()]

    def get_queryset(self):
        return scope_group(Meeting.objects.select_related("created_by"), self.request.user).prefetch_related(
            Prefetch("agenda", AgendaItem.objects.select_related("presenter")),
            Prefetch("actions", ActionItem.objects.select_related("owner", "carried_to")),
            Prefetch("files", MeetingFile.objects.select_related("uploaded_by")),
        )

    def perform_create(self, serializer):
        serializer.save(group=self.request.user.group, created_by=self.request.user)

    def perform_destroy(self, meeting):
        with transaction.atomic():
            # Locked, then the files read afresh (not the list fetched with the page): an upload just before is included.
            meeting = get_object_or_404(Meeting.objects.select_for_update(), pk=meeting.pk)
            delete_on_commit([f.file for f in MeetingFile.objects.filter(meeting=meeting)])
            meeting.delete()

    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser])
    def files(self, request, pk=None):
        meeting = self.get_object()
        presenting = any(item.presenter_id == request.user.id for item in meeting.agenda.all())
        if not (presenting or is_supervisor(request.user)):
            raise PermissionDenied("只有议程里的汇报人、导师和管理员可以上传附件")
        uploaded, name = checked_upload(request)
        meeting_file = MeetingFile(meeting=meeting, name=name, size=uploaded.size, uploaded_by=request.user)
        meeting_file.file.save(name, uploaded, save=False)  # written before the lock: a big file must not hold it
        try:
            with transaction.atomic():
                # a meeting deleted meanwhile is a 404, not a database error
                get_object_or_404(Meeting.objects.select_for_update(), pk=meeting.pk)
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
        if not (meeting_file.uploaded_by_id == self.request.user.id or is_supervisor(self.request.user)):
            raise PermissionDenied("只有上传人、导师和管理员可以删除附件")
        with transaction.atomic():
            delete_on_commit([meeting_file.file])
            meeting_file.delete()


class DoneSerializer(serializers.Serializer):
    done = serializers.BooleanField()


class ActionItemViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """The group's items across meetings, most urgent first, and marking one done or not: the owner or a manager.
    The rest is edited with the meeting."""

    serializer_class = MyActionItemSerializer

    def get_queryset(self):
        items = scope_group(
            ActionItem.objects.select_related("owner", "meeting", "carried_to"), self.request.user, "meeting__group"
        )
        if self.action != "list":
            return items
        params = self.request.query_params
        if (state := params.get("open")) in ("1", "0"):
            items = items.filter(done_at__isnull=state == "1")
        if params.get("overdue") == "1":
            items = items.filter(done_at__isnull=True, due_date__lt=timezone.localdate())
        if owner := params.get("owner"):
            items = items.filter(owner_id=plain_int(owner)) if plain_int(owner) else items.none()
        return items.order_by(F("due_date").asc(nulls_last=True), "-meeting__date", "id")

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
