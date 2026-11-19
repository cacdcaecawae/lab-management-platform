from django.db import IntegrityError, transaction
from django.db.models import F, Func, Max, Q, TextField, Value
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from core.exceptions import Conflict
from core.files import checked_upload, delete_on_commit, download, sha256_of
from core.history import serialize_history
from core.permissions import IsActiveMember, IsManager, is_manager, scope_group

from .models import Doc, DocVersion
from .serializers import DocDetailSerializer, DocSerializer, DocVersionSerializer


class DocViewSet(viewsets.ModelViewSet):
    """Group-wide read; everyone creates; the author or a manager edits and adds versions; only managers delete."""

    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_permissions(self):
        if self.action == "destroy":
            return [IsActiveMember(), IsManager()]
        return [IsActiveMember()]

    def get_serializer_class(self):
        return DocSerializer if self.action == "list" else DocDetailSerializer

    def get_queryset(self):
        docs = scope_group(Doc.objects.select_related("equipment", "author"), self.request.user).prefetch_related(
            "versions__uploaded_by"
        )
        if self.action != "list":  # list filters must not turn detail URLs into 404s
            return docs
        params = self.request.query_params
        if keyword := params.get("search", "").strip():
            # Substring match: PostgreSQL's full-text search does not split Chinese words.
            # shortcut: a sequential scan; add pg_trgm indexes on title/description if thousands of docs get slow.
            docs = docs.annotate(
                tag_text=Func(F("tags"), Value(" "), function="array_to_string", output_field=TextField())
            ).filter(
                Q(title__icontains=keyword) | Q(description__icontains=keyword) | Q(tag_text__icontains=keyword)
                | Q(equipment__code__icontains=keyword) | Q(equipment__name__icontains=keyword)
            )
        if category := params.get("category"):
            docs = docs.filter(category=category) if category in Doc.Category.values else docs.none()
        if equipment := params.get("equipment"):
            docs = docs.filter(equipment_id=equipment) if equipment.isdigit() else docs.none()
        if tag := params.get("tag"):
            docs = docs.filter(tags__contains=[tag])
        return docs

    def check_writer(self, doc):
        if not (doc.author_id == self.request.user.id or is_manager(self.request.user)):
            raise PermissionDenied("只有作者和管理员可以修改这篇文档")

    def perform_create(self, serializer):
        serializer.save(group=self.request.user.group, author=self.request.user)

    def perform_update(self, serializer):
        self.check_writer(serializer.instance)
        serializer.save()

    def perform_destroy(self, doc):
        with transaction.atomic():
            delete_on_commit([v.file for v in doc.versions.all()])
            doc.delete()

    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser])
    def versions(self, request, pk=None):
        """A new file version; earlier versions are kept."""
        doc = self.get_object()
        self.check_writer(doc)
        uploaded, name = checked_upload(request)
        version = DocVersion(
            doc=doc, name=name, size=uploaded.size, sha256=sha256_of(uploaded),
            note=str(request.data.get("note", "")).strip()[:200], uploaded_by=request.user,
        )
        version.file.save(name, uploaded, save=False)  # written before the lock: a big file must not hold it
        try:
            with transaction.atomic():
                Doc.objects.select_for_update().get(pk=doc.pk)  # numbers count up one at a time
                version.number = (doc.versions.aggregate(n=Max("number"))["n"] or 0) + 1
                version.save()
                # update(), not save(): a new file is not a change of the document's fields (no history entry)
                Doc.objects.filter(pk=doc.pk).update(updated_at=timezone.now())
        except IntegrityError:
            version.file.delete(save=False)
            raise Conflict("同时有人在上传新版本，请重试")
        except Exception:
            version.file.delete(save=False)  # the row is not there: the file must not stay behind
            raise
        return Response(DocVersionSerializer(version).data, status=status.HTTP_201_CREATED)

    @action(detail=True, url_path=r"versions/(?P<number>\d+)/file")
    def version_file(self, request, pk=None, number=None):
        version = get_object_or_404(self.get_object().versions, number=number)
        return download(version.file, version.name)

    @action(detail=True)
    def history(self, request, pk=None):
        return Response(serialize_history(self.get_object()))
