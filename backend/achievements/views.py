import re
import tempfile
import zipfile

from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.http import content_disposition_header
from openpyxl import Workbook
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from core.export import xlsx_bytes
from core.files import checked_upload, delete_name_on_commit, delete_on_commit, download
from core.filters import Ordering
from core.history import serialize_history
from core.params import plain_int, search_text
from core.permissions import IsActiveMember, IsManager, is_manager, scope_group

from .models import Achievement
from .queries import filter_status
from .serializers import AchievementSerializer
from .stats import export_stats, stats as build_stats

FULLTEXT_TYPES = {".pdf"}
FULLTEXT_MAX_SIZE = 50 * 1024**2
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def file_safe(title):
    return re.sub(r'[\\/:*?"<>|\s]+', "_", title).strip("_")[:60] or "全文"


class AchievementViewSet(viewsets.ModelViewSet):
    """Group-wide read; everyone registers; the registrant, member authors and managers edit; only managers delete."""

    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    serializer_class = AchievementSerializer
    filter_backends = [Ordering]
    ordering_fields = ["date"]

    def get_permissions(self):
        if self.action == "destroy":
            return [IsActiveMember(), IsManager()]
        return [IsActiveMember()]

    def get_queryset(self):
        items = scope_group(Achievement.objects.select_related("created_by"), self.request.user).prefetch_related("members")
        return self.filtered(items) if self.action in ("list", "export") else items

    def filtered(self, items):
        """Shared by the list and the export, so the export holds exactly what the page shows."""
        params = self.request.query_params
        if item := params.get("item"):
            return items.filter(pk=item) if plain_int(item) else items.none()
        if kind := params.get("type"):
            items = items.filter(type=kind) if kind in Achievement.Type.values else items.none()
        items = filter_status(items, params.get("status"))
        if year := params.get("year"):
            if plain_int(year, 4) is None:
                raise ValidationError({"year": ["年份应为数字"]})
            items = items.filter(date__year=int(year))
        if member := params.get("member"):
            items = items.filter(members=member) if plain_int(member) else items.none()
        if (fulltext := params.get("has_fulltext")) in ("1", "0"):
            items = items.exclude(fulltext="") if fulltext == "1" else items.filter(fulltext="")
        if keyword := search_text(params):
            items = items.filter(Q(title__icontains=keyword) | Q(authors__icontains=keyword) | Q(venue__icontains=keyword))
        return items

    def check_writer(self, achievement):
        user = self.request.user
        mine = achievement.created_by_id == user.id or achievement.members.filter(pk=user.pk).exists()
        if not (mine or is_manager(user)):
            raise PermissionDenied("只有登记人、署名的本组成员和管理员可以修改")

    def perform_create(self, serializer):
        serializer.save(group=self.request.user.group, created_by=self.request.user)

    def perform_update(self, serializer):
        self.check_writer(serializer.instance)
        serializer.save()

    def perform_destroy(self, achievement):
        with transaction.atomic():
            # Locked, then re-read: a full text replaced just before is the one to delete.
            achievement = get_object_or_404(Achievement.objects.select_for_update(), pk=achievement.pk)
            delete_on_commit([achievement.fulltext])
            achievement.delete()

    @action(detail=True, methods=["get", "post", "delete"], parser_classes=[MultiPartParser])
    def fulltext(self, request, pk=None):
        achievement = self.get_object()
        if request.method == "GET":
            if not achievement.fulltext:
                raise NotFound("还没有上传全文")
            return download(achievement.fulltext, achievement.fulltext_name)
        self.check_writer(achievement)
        with transaction.atomic():
            # Locked: a second upload at the same time waits and then replaces this file, instead of orphaning it.
            achievement = Achievement.objects.select_for_update().get(pk=achievement.pk)
            # The name, not the FieldFile: saving a new file renames that same object.
            storage, old_name = achievement.fulltext.storage, achievement.fulltext.name
            if request.method == "POST":
                uploaded, name = checked_upload(request, FULLTEXT_MAX_SIZE, FULLTEXT_TYPES)
                achievement.fulltext.save(name, uploaded, save=False)
                achievement.fulltext_name = name
            else:
                achievement.fulltext, achievement.fulltext_name = "", ""
            new_name = achievement.fulltext.name
            try:
                with transaction.atomic():
                    achievement.save(update_fields=["fulltext", "fulltext_name", "updated_at"])
                    if old_name:  # the replaced or removed file
                        delete_name_on_commit(storage, old_name)
            except Exception:
                if new_name:
                    storage.delete(new_name)
                raise
        return Response(self.get_serializer(achievement).data)

    @action(detail=True)
    def history(self, request, pk=None):
        return Response(serialize_history(self.get_object()))

    @action(detail=False)
    def stats(self, request):
        return Response(build_stats(self.get_queryset(), request.user.group_id, request.query_params))

    @action(detail=False, url_path="stats/export")
    def stats_export(self, request):
        return export_stats(build_stats(self.get_queryset(), request.user.group_id, request.query_params))

    @action(detail=False)
    def export(self, request):
        """The filtered list as .xlsx; with files=1 a .zip of the list plus every full text, named by row number."""
        items = self.get_queryset()
        items = list(self.filter_queryset(items) if request.query_params.get("ordering") else items.order_by("type", "date", "id"))
        with_files = request.query_params.get("files") == "1"
        book = Workbook()
        sheet = book.active
        sheet.title = "成果清单"
        sheet.append(["序号", "类型", "标题", "作者", "本组成员", "出处 / 编号", "日期", "状态", "DOI / 链接", "全文"])
        files = []
        for row, a in enumerate(items, 1):
            path = ""
            if with_files and a.fulltext:
                if a.fulltext.storage.exists(a.fulltext.name):
                    path = f"全文/{row:03d}-{file_safe(a.title)}.pdf"
                    files.append((path, a.fulltext))
                else:  # lost from storage: said in the table instead of failing the whole export
                    path = "（文件缺失）"
            sheet.append([
                row, a.get_type_display(), a.title, a.authors, "、".join(m.display_name for m in a.members.all()), a.venue,
                a.date, a.get_status_display(), a.link, path or ("（无）" if with_files else ("有" if a.fulltext else "")),
            ])
        for cell in sheet["G"][1:]:
            cell.number_format = "yyyy-mm-dd"
        table = xlsx_bytes(book)
        stamp = timezone.localdate().strftime("%Y%m%d")
        if not with_files:
            response = HttpResponse(table, content_type=XLSX)
            response["Content-Disposition"] = content_disposition_header(as_attachment=True, filename=f"成果清单-{stamp}.xlsx")
            return response
        # Spooled: small exports stay in memory, large ones go to a temp file instead of filling it.
        bundle = tempfile.SpooledTemporaryFile(max_size=50 * 1024**2)
        with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("成果清单.xlsx", table)
            for path, field_file in files:
                with field_file.open("rb") as source, archive.open(path, "w") as target:
                    for chunk in iter(lambda: source.read(1024**2), b""):
                        target.write(chunk)
        bundle.seek(0)
        return FileResponse(bundle, as_attachment=True, filename=f"成果清单与全文-{stamp}.zip")
