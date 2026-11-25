import os
import shutil
import tempfile
import zipfile

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Count, Prefetch, ProtectedError, Q, Sum
from django.http import FileResponse
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from core.exceptions import Conflict
from core.files import FileTooLarge, clean_file_name, delete_on_commit, open_stored, sha256_of
from core.filters import Ordering, Search
from core.permissions import IsActiveMember, IsOwnerOrReadOnly, scope_private, scope_research
from core.preview import preview_response

from .models import DataFile, Dataset, DatasetSnapshot
from .queries import scope_datasets
from .serializers import DataFileSerializer, DatasetSerializer
from .versions import lock_datasets, locked_file_ids

DEFAULT_DATASET_ZIP_MAX_BYTES = 200 * 1024 * 1024  # 200 MB


class DatasetTooLargeForZip(APIException):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    default_detail = "数据集文件总大小超过打包上限，请逐个下载。"
    default_code = "too_large_for_zip"


def clean_path(raw):
    """A path inside a dropped folder ("采集/ch1/wave.csv"): its parts joined by "/", without empty, "." or ".." ones."""
    parts = (part.strip() for part in raw.replace("\\", "/").split("/"))
    return "/".join(part for part in parts if part and part not in (".", ".."))


def save_uploads(dataset, user, uploads, client_sha256, path=""):
    """Validate every upload first, then save all of them or none. `path`: the file's place in a dropped folder,
    kept as its name so the same file name in two subfolders does not collide."""
    if not uploads:
        raise ValidationError({"file": ["请选择要上传的文件"]})
    if client_sha256 and len(uploads) > 1:
        raise ValidationError({"sha256": ["只有上传单个文件时才能提供校验值"]})
    if path and len(uploads) > 1:
        raise ValidationError({"path": ["只有上传单个文件时才能提供路径"]})

    names = []
    for uploaded in uploads:
        # UploadedFile cuts its own names to 255 chars, the DataFile.name limit; a path may be longer.
        name = clean_path(path) if path else clean_file_name(uploaded.name or "")
        if not name or "\x00" in name or len(name) > 255:
            raise ValidationError({"file": [f"文件名无效：{(path or uploaded.name)!r}"]})
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

    written = []
    try:
        with transaction.atomic():
            created = []
            for uploaded, name, digest in zip(uploads, names, hashes):
                data_file = DataFile(dataset=dataset, name=name, size=uploaded.size, sha256=digest, uploaded_by=user)
                data_file.file.save(name, uploaded, save=False)
                written.append(data_file.file)
                data_file.save()
                created.append(data_file)
    except Exception as exc:
        # The rolled-back rows must not leave their files behind in storage.
        for file in written:
            file.delete(save=False)
        if isinstance(exc, IntegrityError):  # a concurrent upload took the same name
            raise Conflict("已存在同名文件", code="file_exists") from exc
        raise
    return created


class DatasetViewSet(viewsets.ModelViewSet):
    serializer_class = DatasetSerializer
    permission_classes = [IsActiveMember, IsOwnerOrReadOnly]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    filter_backends = [Search, Ordering]
    search_fields = ["name"]
    code_prefix = "DS"
    ordering_fields = ["updated_at", "total_size"]

    def get_queryset(self):
        # Explicit order_by: Django drops Meta.ordering on aggregated (GROUP BY) querysets.
        queryset = (
            scope_datasets(Dataset.objects.select_related("project", "owner"), self.request.user)
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
        # raw_of: the experiment whose own raw data this is; such a dataset goes with its record (research views).
        relations = ["files", "raw_of", "experiments", "used_by_runs", "script_of_runs", "produced_by_runs", "weekly_reports"]
        used = Q()
        for relation in relations:
            used |= Q(**{f"{relation}__isnull": False})
        if Dataset.objects.filter(used, pk=instance.pk).exists():
            raise Conflict("数据集已有文件或已被实验、处理记录、周报引用，不能删除", code="invalid_state")
        try:
            with transaction.atomic():
                instance.delete()
        except ProtectedError:
            raise Conflict("数据集刚被引用，不能删除", code="invalid_state") from None

    def _files_for_version(self, dataset, version_param):
        # Not dataset.files: that reuses the version prefetch, which loads only name + sha256.
        files = DataFile.objects.filter(dataset=dataset).select_related("uploaded_by")
        if version_param:
            if "\x00" in version_param:  # PostgreSQL cannot compare it; no digest holds one anyway
                raise NotFound("没有这个版本")
            # The file list of a version pinned by a submitted record.
            snapshot = dataset.snapshots.filter(digest=version_param.strip().lower()).first()
            if snapshot is None:
                raise NotFound("没有这个版本")
            files = files.filter(snapshots=snapshot)
        return files

    @action(detail=True, methods=["get", "post"], parser_classes=[MultiPartParser])
    def files(self, request, pk=None):
        dataset = self.get_object()  # out of scope -> 404; POST by a non-owner -> 403
        if request.method == "GET":
            files = self._files_for_version(dataset, request.query_params.get("version"))
            return Response(DataFileSerializer(files, many=True, context={"locked": locked_file_ids(dataset.pk)}).data)
        client_sha256 = request.data.get("sha256", "").strip().lower()
        path = request.data.get("path", "")
        created = save_uploads(dataset, request.user, request.FILES.getlist("file"), client_sha256, path)
        return Response(DataFileSerializer(created, many=True).data, status=status.HTTP_201_CREATED)

    @action(detail=True, url_path="download-zip")
    def download_zip(self, request, pk=None):
        dataset = self.get_object()
        version_param = request.query_params.get("version")
        files = list(self._files_for_version(dataset, version_param))
        if not files:
            raise Conflict("数据集里还没有文件。", code="empty_dataset")
        max_bytes = getattr(settings, "DATASET_ZIP_MAX_BYTES", DEFAULT_DATASET_ZIP_MAX_BYTES)
        if sum(f.size for f in files) > max_bytes:
            limit_hint = f"（{max_bytes // (1024 * 1024)} MB）" if max_bytes >= 1024 * 1024 else ""
            raise DatasetTooLargeForZip(f"数据集文件总大小超过打包上限{limit_hint}，请逐个下载。")

        temp_dir = getattr(settings, "FILE_UPLOAD_TEMP_DIR", None)
        buf = tempfile.SpooledTemporaryFile(
            max_size=10 * 1024 * 1024,
            dir=temp_dir if temp_dir and os.path.isdir(temp_dir) else None,
        )
        try:
            with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as zf:
                for data_file in files:
                    arcname = clean_path(data_file.name) or f"file-{data_file.pk}"  # a dropped folder's layout
                    with data_file.file.open("rb") as src, zf.open(arcname, "w") as dst:
                        shutil.copyfileobj(src, dst, 64 * 1024)
        except FileNotFoundError:
            buf.close()
            raise NotFound("数据集有文件已缺失，无法打包下载。") from None
        except Exception:
            buf.close()
            raise
        buf.seek(0)
        version_tag = version_param.strip()[:12] if version_param else ""
        filename = f"{dataset.code}-{version_tag}.zip" if version_tag else f"{dataset.code}.zip"
        resp = FileResponse(buf, as_attachment=True, filename=filename, content_type="application/zip")
        resp["Cache-Control"] = "private, no-store"
        return resp

    @action(detail=True)
    def references(self, request, pk=None):
        """The records citing this dataset that the user may see, through reverse relations (datasets does not import
        research or reports). The experiment holding it as its raw data is among the experiments, and runs and weekly
        reports citing that experiment cite its data."""
        dataset = self.get_object()
        experiment_model, run_model = dataset.experiments.model, dataset.used_by_runs.model
        report_model = dataset.weekly_reports.model
        holders = experiment_model.objects.filter(Q(pk__in=dataset.experiments.values("pk")) | Q(dataset=dataset))
        experiments = [
            {"id": e.id, "code": e.code, "title": e.title, "status": e.status}
            for e in scope_research(holders.only("id", "title", "status", "created_at", "date", "owner_id"), request.user)
            .order_by("-date", "-id")
        ]
        run_map = {}
        sources = [
            (dataset.used_by_runs.all(), "input"),
            (run_model.objects.filter(experiments__dataset=dataset), "input"),
            (dataset.script_of_runs.all(), "script"),
            (dataset.produced_by_runs.all(), "output"),
        ]
        for runs, role in sources:
            for run in scope_research(runs.only("id", "title", "status", "created_at", "owner_id"), request.user):
                entry = run_map.setdefault(
                    run.id,
                    {"id": run.id, "code": run.code, "title": run.title, "status": run.status, "roles": []},
                )
                if role not in entry["roles"]:
                    entry["roles"].append(role)
        runs = sorted(run_map.values(), key=lambda r: -r["id"])
        citing = Q(pk__in=dataset.weekly_reports.values("pk")) | Q(
            pk__in=report_model.objects.filter(experiments__dataset=dataset).values("pk")
        )
        reports = [
            {
                "id": r.id,
                "week_start": r.week_start.isoformat(),
                "status": r.status,
                "owner": {"id": r.owner_id, "name": r.owner.name},
            }
            for r in scope_private(
                report_model.objects.filter(citing).select_related("owner").only(
                    "id", "week_start", "status", "owner_id", "owner__id", "owner__name"
                ),
                request.user,
            ).order_by("-week_start", "-id")
        ]
        return Response({"experiments": experiments, "runs": runs, "reports": reports})


class DataFileViewSet(mixins.RetrieveModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    serializer_class = DataFileSerializer

    def get_queryset(self):
        files = DataFile.objects.select_related("uploaded_by", "dataset")
        return scope_datasets(files, self.request.user, owner_field="dataset__owner", dataset_field="dataset_id")

    def destroy(self, request, *args, **kwargs):
        """The owner takes back a mistaken upload. A file in a version that a submitted record pins stays (409)."""
        data_file = self.get_object()
        if data_file.dataset.owner_id != request.user.id:
            raise PermissionDenied("只能删除自己记录里的文件")
        with transaction.atomic():
            lock_datasets([data_file.dataset_id])  # a submit pinning this dataset now goes first or waits
            data_file = DataFile.objects.filter(pk=data_file.pk).first()
            if data_file is None:
                raise NotFound("文件已删除")
            if data_file.pk in locked_file_ids(data_file.dataset_id):
                raise Conflict("文件在已提交记录引用的版本里，不能删除", code="invalid_state")
            # No submitted record pins these snapshots (or the file would be locked); a snapshot left without the file
            # would still be reused by a later pin of its version code.
            DatasetSnapshot.objects.filter(files=data_file).delete()
            delete_on_commit([data_file.file])
            data_file.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True)
    def download(self, request, pk=None):
        data_file = self.get_object()
        name = clean_file_name(data_file.name)  # a file from a dropped folder downloads under its own name
        return FileResponse(open_stored(data_file.file), as_attachment=True, filename=name)

    @action(detail=True)
    def preview(self, request, pk=None):
        data_file = self.get_object()
        raw = request.query_params.get("raw") == "1"
        return preview_response(data_file.file, data_file.name, size=data_file.size, raw=raw)
