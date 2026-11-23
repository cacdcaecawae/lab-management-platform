from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Count, Prefetch, ProtectedError, Sum
from django.http import FileResponse
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.filters import SearchFilter
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from core.exceptions import Conflict
from core.files import FileTooLarge, clean_file_name, open_stored, sha256_of
from core.permissions import IsActiveMember, IsOwnerOrReadOnly, scope_private

from .models import DataFile, Dataset
from .serializers import DataFileSerializer, DatasetSerializer


def save_uploads(dataset, user, uploads, client_sha256):
    """Validate every upload first, then save all of them or none."""
    if not uploads:
        raise ValidationError({"file": ["请选择要上传的文件"]})
    if client_sha256 and len(uploads) > 1:
        raise ValidationError({"sha256": ["只有上传单个文件时才能提供校验值"]})

    names = []
    for uploaded in uploads:
        # No length check: UploadedFile already cuts names to 255 chars, the DataFile.name limit.
        name = clean_file_name(uploaded.name or "")
        if not name:
            raise ValidationError({"file": [f"文件名无效：{uploaded.name!r}"]})
        if uploaded.size > settings.MAX_UPLOAD_SIZE:
            raise FileTooLarge(f"{name} 超过单个文件上限 {settings.MAX_UPLOAD_SIZE} 字节")
        names.append(name)

    taken = set(dataset.files.filter(name__in=names).values_list("name", flat=True))
    taken |= {name for name in names if names.count(name) > 1}
    if taken:
        raise Conflict(f"已存在同名文件：{'、'.join(sorted(taken))}", code="file_exists")

    hashes = [sha256_of(uploaded) for uploaded in uploads]
    if client_sha256 and client_sha256 != hashes[0]:
        raise ValidationError({"sha256": ["校验值与服务器计算结果不一致，文件可能在传输中损坏"]})

    storage = DataFile._meta.get_field("file").storage
    written = []
    try:
        with transaction.atomic():
            created = []
            for uploaded, name, digest in zip(uploads, names, hashes):
                data_file = DataFile(dataset=dataset, name=name, size=uploaded.size, sha256=digest, uploaded_by=user)
                planned = data_file.file.field.generate_filename(data_file, name)  # upload_to's server-generated path
                written.append(planned)
                data_file.file.name = storage.save(planned, uploaded, max_length=data_file.file.field.max_length)
                written[-1] = data_file.file.name
                data_file.save()
                created.append(data_file)
    except Exception as exc:
        # The rolled-back rows must not leave their files behind in storage.
        for path in written:
            storage.delete(path)
        if isinstance(exc, IntegrityError):  # a concurrent upload took the same name
            raise Conflict("已存在同名文件", code="file_exists") from exc
        raise
    return created


class DatasetViewSet(viewsets.ModelViewSet):
    serializer_class = DatasetSerializer
    permission_classes = [IsActiveMember, IsOwnerOrReadOnly]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    filter_backends = [SearchFilter]
    search_fields = ["name"]

    def get_queryset(self):
        # Explicit order_by: Django drops Meta.ordering on aggregated (GROUP BY) querysets.
        queryset = (
            scope_private(Dataset.objects.select_related("project", "owner"), self.request.user)
            .annotate(file_count=Count("files"), total_size=Sum("files__size", default=0))
            # name + sha256 of every file, for the current version code.
            # shortcut: list pages load these for every dataset on the page; store the version on Dataset if datasets reach many thousands of files.
            .prefetch_related(Prefetch("files", queryset=DataFile.objects.only("dataset", "name", "sha256")))
            .order_by("-created_at", "-id")
        )
        if self.action != "list":  # list filters must not turn detail URLs into 404s
            return queryset
        params = self.request.query_params
        for field in ("project", "owner"):
            if params.get(field):
                try:
                    queryset = queryset.filter(**{f"{field}_id": int(params[field])})
                except ValueError:
                    raise ValidationError({field: ["必须是整数"]}) from None
        if params.get("kind"):
            if params["kind"] not in Dataset.Kind.values:
                return queryset.none()
            queryset = queryset.filter(kind=params["kind"])
        return queryset

    # Re-read after writes so the response carries the annotated file_count / total_size.
    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
        serializer.instance = self.get_queryset().get(pk=serializer.instance.pk)

    def perform_update(self, serializer):
        serializer.save()
        serializer.instance = self.get_queryset().get(pk=serializer.instance.pk)

    def perform_destroy(self, instance):
        relations = ["files", "experiments", "used_by_runs", "script_of_runs", "produced_by_runs", "weekly_reports"]
        if any(getattr(instance, relation).exists() for relation in relations):
            raise Conflict("数据集已有文件或已被实验、处理记录、周报引用，不能删除", code="invalid_state")
        try:
            with transaction.atomic():
                instance.delete()
        except ProtectedError:
            raise Conflict("数据集刚被引用，不能删除", code="invalid_state") from None

    @action(detail=True, methods=["get", "post"], parser_classes=[MultiPartParser])
    def files(self, request, pk=None):
        dataset = self.get_object()  # out of scope -> 404; POST by a non-owner -> 403
        if request.method == "GET":
            # Not dataset.files: that reuses the version prefetch, which loads only name + sha256.
            files = DataFile.objects.filter(dataset=dataset).select_related("uploaded_by")
            if request.query_params.get("version"):
                # The file list of a version pinned by a submitted record.
                snapshot = dataset.snapshots.filter(digest=request.query_params["version"].strip().lower()).first()
                if snapshot is None:
                    raise NotFound("没有这个版本")
                files = files.filter(snapshots=snapshot)
            return Response(DataFileSerializer(files, many=True).data)
        client_sha256 = request.data.get("sha256", "").strip().lower()
        created = save_uploads(dataset, request.user, request.FILES.getlist("file"), client_sha256)
        return Response(DataFileSerializer(created, many=True).data, status=status.HTTP_201_CREATED)


class DataFileViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = DataFileSerializer

    def get_queryset(self):
        files = DataFile.objects.select_related("uploaded_by")
        return scope_private(files, self.request.user, owner_field="dataset__owner")

    @action(detail=True)
    def download(self, request, pk=None):
        data_file = self.get_object()
        return FileResponse(open_stored(data_file.file), as_attachment=True, filename=data_file.name)
