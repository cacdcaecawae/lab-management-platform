from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from core.exceptions import Conflict
from core.files import checked_upload, delete_on_commit, download
from core.filters import Ordering, Search
from core.history import serialize_history
from core.notifications import notify
from core.permissions import IsActiveMember, IsAdvisor, IsOwnerOrReadOnly, scope_research
from datasets.models import DataFile, Dataset
from datasets.versions import locked_file_ids, pin_versions

from .models import Experiment, ExperimentPhoto, ProcessingRun, RecordStatus
from .serializers import ExperimentPhotoSerializer, ExperimentSerializer, ProcessingRunSerializer, ReturnSerializer

PHOTO_TYPES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
PHOTO_MAX_BYTES = 20 * 1024**2


def used_by_this_record_only(dataset):
    """No other experiment, run or weekly report uses the dataset (as raw data, a link, input, script or results)."""
    experiments = Experiment.objects.filter(Q(dataset=dataset) | Q(datasets=dataset)).distinct().count()
    runs = ProcessingRun.objects.filter(Q(script_dataset=dataset) | Q(output_dataset=dataset) | Q(inputs=dataset)).distinct()
    return experiments + runs.count() + dataset.weekly_reports.count() == 1


def discard(dataset):
    """A deleted record's own files: the rows now, the stored files once the deletion commits."""
    files = DataFile.objects.filter(dataset=dataset)
    delete_on_commit([f.file for f in files])
    dataset.snapshots.all().delete()
    files.delete()
    dataset.delete()


class RecordViewSet(viewsets.ModelViewSet):
    """Shared behaviour of experiments and processing runs: research scope (core.permissions.scope_research), the
    owner edits drafts only, submit / return / history. Subclasses set queryset, serializer_class, label and page (for
    the notification a return sends the owner), filters, submit_errors(), own_files() and removable_files()."""

    http_method_names = ["get", "post", "patch", "delete", "head", "options"]  # PUT is not in the contract
    filter_backends = [Search, Ordering]
    search_fields = ["title"]
    filters = {"project": "project", "owner": "owner", "status": "status"}  # list ?param= -> lookup

    def get_permissions(self):
        if self.action == "return_to_draft":
            return [IsActiveMember(), IsAdvisor()]
        return [IsActiveMember(), IsOwnerOrReadOnly()]

    def get_queryset(self):
        queryset = scope_research(super().get_queryset(), self.request.user)
        if self.action != "list":  # list filters must not turn detail URLs into 404s
            return queryset
        params = self.request.query_params
        if params.get("status") and params["status"] not in RecordStatus.values:
            return queryset.none()  # also keeps NUL bytes, which PostgreSQL rejects with a 500, out of the query
        lookups = {lookup: params[name] for name, lookup in self.filters.items() if params.get(name)}
        try:
            return queryset.filter(**lookups)
        except ValueError:  # e.g. ?project=abc
            raise ValidationError({"non_field_errors": ["过滤参数格式不正确"]})

    def submit_errors(self, obj):
        """{field: [message]} for whatever is missing before obj can be submitted."""
        raise NotImplementedError

    def own_files(self, obj):
        """Ids of the datasets holding the record's own files (they follow its project)."""
        raise NotImplementedError

    def removable_files(self, obj):
        """The datasets to delete with the draft obj; raises Conflict when obj may not be deleted."""
        raise NotImplementedError

    def lock_object(self):
        # get_object() applies the scope (404) and owner/role checks (403). Lock in a separate
        # query: FOR UPDATE cannot be combined with the nullable outer joins of select_related.
        obj = self.get_object()
        return type(obj).objects.select_for_update().get(pk=obj.pk)

    def lock_draft(self):
        obj = self.lock_object()
        if obj.status != RecordStatus.DRAFT:
            raise Conflict("已提交的记录不能修改或删除，请先由导师退回", code="invalid_state")
        return obj

    def update(self, request, *args, **kwargs):
        # Locked so a concurrent submit cannot be overwritten back to draft by this save.
        with transaction.atomic():
            serializer = self.get_serializer(self.lock_draft(), data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            record = serializer.save()
            if "project" in serializer.validated_data:  # a corrected project: the record's files go with it
                Dataset.objects.filter(pk__in=self.own_files(record)).update(project=record.project)
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        with transaction.atomic():
            obj = self.lock_draft()
            if obj.weekly_reports.exists():
                raise Conflict("该记录已被周报引用，不能删除", code="invalid_state")
            removable = self.removable_files(obj)
            obj.delete()
            for dataset in removable:
                discard(dataset)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        with transaction.atomic():
            obj = self.lock_object()
            if obj.status != RecordStatus.DRAFT:
                raise Conflict("只有草稿可以提交", code="invalid_state")
            errors = self.submit_errors(obj)
            if errors:
                raise ValidationError(errors)
            obj.status = RecordStatus.SUBMITTED
            obj.submitted_at = timezone.now()
            obj.data_versions = pin_versions(obj.cited_datasets())
            obj.save()
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["post"], url_path="return")
    def return_to_draft(self, request, pk=None):
        body = ReturnSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        with transaction.atomic():
            obj = self.lock_object()
            if obj.status != RecordStatus.SUBMITTED:
                raise Conflict("只有已提交的记录可以退回", code="invalid_state")
            obj.status = RecordStatus.DRAFT
            obj.submitted_at = None
            obj.data_versions = {}  # a draft follows the datasets' latest files; the next submit pins again
            reason = body.validated_data["reason"]
            obj._change_reason = reason
            obj.save()
            notify(obj.owner.group_id, f"{self.label}被退回", f"{self.page}{obj.pk}",
                   recipient_ids=[obj.owner_id], exclude_ids=[request.user.id], body=f"{obj.title}：{reason}")
        return Response(self.get_serializer(obj).data)

    @action(detail=True)
    def history(self, request, pk=None):
        return Response(serialize_history(self.get_object()))


class ExperimentViewSet(RecordViewSet):
    label, page = "实验记录", "/experiments/"  # the returned-record notification
    code_prefix, ordering_fields = "EX", ["date", "updated_at"]
    # ?equipment_item= / ?specimen=: the records naming a device or a specimen (their detail pages)
    filters = {**RecordViewSet.filters, "equipment_item": "equipment_item", "specimen": "specimen_items"}
    queryset = (
        Experiment.objects.select_related("owner", "project", "equipment_item", "dataset")
        .prefetch_related("datasets", "specimen_items", Prefetch("photos", ExperimentPhoto.objects.select_related("uploaded_by")))
        .annotate(file_count=Count("dataset__files"))
        .order_by("-date", "-id")  # Meta.ordering does not apply to an aggregated (GROUP BY) queryset
    )
    serializer_class = ExperimentSerializer

    def perform_create(self, serializer):
        user, data = self.request.user, serializer.validated_data
        with transaction.atomic():
            files = Dataset.objects.create(owner=user, project=data.get("project"), name=data["title"], kind=Dataset.Kind.RAW)
            serializer.save(owner=user, dataset=files)

    def submit_errors(self, experiment):
        required = {"title": experiment.title, "date": experiment.date}
        return {field: ["提交前必须填写"] for field, value in required.items() if not value}

    def own_files(self, experiment):
        return [experiment.dataset_id]

    def removable_files(self, experiment):
        """An unused draft goes with its raw data and photos."""
        if experiment.runs.exists():
            raise Conflict("该记录已被数据处理引用，不能删除", code="invalid_state")
        dataset = experiment.dataset
        if dataset is not None and not used_by_this_record_only(dataset):
            raise Conflict("这条记录的原始数据还被其他记录引用，不能删除", code="invalid_state")
        if dataset is not None and locked_file_ids(dataset.pk):
            raise Conflict("原始数据里有文件在已提交记录引用的版本里，不能删除", code="invalid_state")
        delete_on_commit([photo.file for photo in experiment.photos.all()])
        return [dataset] if dataset else []

    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser])
    def photos(self, request, pk=None):
        """The owner adds a scene photo or a figure while the record is a draft."""
        experiment = self.get_object()  # out of scope: 404; not the owner: 403
        if experiment.status != RecordStatus.DRAFT:
            raise Conflict("已提交的记录不能再加照片", code="invalid_state")
        uploaded, name = checked_upload(request, max_size=PHOTO_MAX_BYTES, types=PHOTO_TYPES)
        photo = ExperimentPhoto(experiment=experiment, name=name, size=uploaded.size, uploaded_by=request.user)
        photo.file.save(name, uploaded, save=False)  # written before the lock: a big file must not hold it
        try:
            with transaction.atomic():
                locked = Experiment.objects.select_for_update().filter(pk=experiment.pk).first()
                if locked is None:  # deleted meanwhile
                    raise NotFound("记录已删除")
                if locked.status != RecordStatus.DRAFT:  # submitted meanwhile
                    raise Conflict("已提交的记录不能再加照片", code="invalid_state")
                photo.save()
        except Exception:
            photo.file.delete(save=False)
            raise
        return Response(ExperimentPhotoSerializer(photo).data, status=status.HTTP_201_CREATED)


class ExperimentPhotoViewSet(mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """A photo opens for whoever sees its experiment; its owner deletes it while the record is a draft. Photos are
    added through the experiment."""

    def get_queryset(self):
        visible = scope_research(Experiment.objects.all(), self.request.user)
        return ExperimentPhoto.objects.filter(experiment__in=visible).select_related("experiment")

    @action(detail=True)
    def file(self, request, pk=None):
        photo = self.get_object()
        return download(photo.file, photo.name)

    def destroy(self, request, *args, **kwargs):
        photo = self.get_object()
        if photo.experiment.owner_id != request.user.id:
            raise PermissionDenied("只能删除自己记录里的照片")
        with transaction.atomic():
            experiment = Experiment.objects.select_for_update().filter(pk=photo.experiment_id).first()
            if experiment is None:  # deleted meanwhile, with its photos
                raise NotFound("记录已删除")
            if experiment.status != RecordStatus.DRAFT:
                raise Conflict("已提交的记录不能删除照片", code="invalid_state")
            delete_on_commit([photo.file])
            photo.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProcessingRunViewSet(RecordViewSet):
    label, page = "数据处理记录", "/runs/"
    code_prefix, ordering_fields = "RUN", ["updated_at"]
    queryset = ProcessingRun.objects.select_related(
        "owner", "project", "script_dataset", "output_dataset"
    ).prefetch_related("inputs", Prefetch("experiments", Experiment.objects.select_related("owner")))
    serializer_class = ProcessingRunSerializer

    def perform_create(self, serializer):
        user, data = self.request.user, serializer.validated_data

        def files(label, kind):
            name = f"{data['title']} · {label}"[:200]
            return Dataset.objects.create(owner=user, project=data.get("project"), name=name, kind=kind)

        with transaction.atomic():
            serializer.save(
                owner=user,
                script_dataset=data.get("script_dataset") or files("脚本", Dataset.Kind.SCRIPT),
                output_dataset=data.get("output_dataset") or files("结果", Dataset.Kind.RESULT),
            )

    def submit_errors(self, run):
        """Reproducibility: someone else must be able to redo this from the record alone."""
        errors = {}
        if not (run.experiments.exists() or run.inputs.exists()):
            errors["experiments"] = ["至少引用 1 条原始数据"]
        else:
            citable = scope_research(Experiment.objects.all(), run.owner).values("pk")
            gone = list(run.experiments.exclude(pk__in=citable))
            if gone:  # e.g. a teammate's record returned to draft since it was picked
                errors["experiments"] = [f"{'、'.join(e.code for e in gone)} 已不能引用（可能已被退回），请移除后再提交"]
        has_scripts = DataFile.objects.filter(dataset_id=run.script_dataset_id).exists()
        if run.script_repo and not run.script_commit:
            errors["script_commit"] = ["填写 git 仓库时必须填写 commit"]
        elif run.script_commit and not run.script_repo:
            errors["script_repo"] = ["填写 commit 时必须填写 git 仓库"]
        elif not (has_scripts or run.script_repo or run.method.strip()):
            errors["script"] = ["请上传脚本文件、填写 git 仓库和 commit，或写明软件/方法说明"]
        if not (DataFile.objects.filter(dataset_id=run.output_dataset_id).exists() or run.conclusion.strip()):
            errors["results"] = ["请上传结果文件或填写结论"]
        return errors

    def own_files(self, run):
        return [run.script_dataset_id, run.output_dataset_id]

    def removable_files(self, run):
        """The run's script and result files go with it, unless another record uses them too (a copied run shares
        its source's scripts)."""
        removable = [d for d in (run.script_dataset, run.output_dataset) if d is not None and used_by_this_record_only(d)]
        if any(locked_file_ids(d.pk) for d in removable):  # cannot happen while nothing else uses them; never break a pin
            raise Conflict("文件在已提交记录引用的版本里，不能删除", code="invalid_state")
        return removable
