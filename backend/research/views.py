from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from core.exceptions import Conflict
from core.filters import Ordering, Search
from core.history import serialize_history
from core.notifications import notify
from core.permissions import IsActiveMember, IsAdvisor, IsOwnerOrReadOnly, scope_private
from datasets.versions import pin_versions

from .models import Experiment, ProcessingRun, RecordStatus
from .serializers import ExperimentSerializer, ProcessingRunSerializer, ReturnSerializer


class RecordViewSet(viewsets.ModelViewSet):
    """Shared behaviour of experiments and processing runs: private scope, the owner edits
    drafts only, submit / return / history. Subclasses set queryset, serializer_class, label and page (for the
    notification a return sends the owner) and submit_errors()."""

    http_method_names = ["get", "post", "patch", "delete", "head", "options"]  # PUT is not in the contract
    filter_backends = [Search, Ordering]
    search_fields = ["title"]

    def get_permissions(self):
        if self.action == "return_to_draft":
            return [IsActiveMember(), IsAdvisor()]
        return [IsActiveMember(), IsOwnerOrReadOnly()]

    def get_queryset(self):
        queryset = scope_private(super().get_queryset(), self.request.user)
        if self.action != "list":  # list filters must not turn detail URLs into 404s
            return queryset
        params = self.request.query_params
        if params.get("status") and params["status"] not in RecordStatus.values:
            return queryset.none()  # also keeps NUL bytes, which PostgreSQL rejects with a 500, out of the query
        lookups = {name: params[name] for name in ("project", "owner", "status") if params.get(name)}
        try:
            return queryset.filter(**lookups)
        except ValueError:  # e.g. ?project=abc
            raise ValidationError({"non_field_errors": ["过滤参数格式不正确"]})

    def submit_errors(self, obj):
        """{field: [message]} for whatever is missing before obj can be submitted."""
        raise NotImplementedError

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

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
            serializer.save()
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        with transaction.atomic():
            obj = self.lock_draft()
            if obj.weekly_reports.exists():
                raise Conflict("该记录已被周报引用，不能删除", code="invalid_state")
            obj.delete()
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
    queryset = Experiment.objects.select_related("owner", "project", "equipment_item").prefetch_related(
        "datasets", "specimen_items"
    )
    serializer_class = ExperimentSerializer

    def submit_errors(self, experiment):
        required = {"title": experiment.title, "date": experiment.date, "project": experiment.project_id}
        return {field: ["提交前必须填写"] for field, value in required.items() if not value}


class ProcessingRunViewSet(RecordViewSet):
    label, page = "数据处理记录", "/runs/"
    code_prefix, ordering_fields = "RUN", ["updated_at"]
    queryset = ProcessingRun.objects.select_related(
        "owner", "project", "script_dataset", "output_dataset"
    ).prefetch_related("inputs")
    serializer_class = ProcessingRunSerializer

    def submit_errors(self, run):
        # Reproducibility: someone else must be able to rerun this from the record alone.
        errors = {}
        if not run.inputs.exists():
            errors["inputs"] = ["至少需要 1 个输入数据"]
        if not run.script_dataset_id:
            if run.script_repo and not run.script_commit:
                errors["script_commit"] = ["填写 git 仓库时必须填写 commit"]
            elif run.script_commit and not run.script_repo:
                errors["script_repo"] = ["填写 commit 时必须填写 git 仓库"]
            elif not run.script_repo:
                errors["script_dataset"] = ["请选择脚本数据集，或填写 git 仓库和 commit"]
        if not run.environment.strip():
            errors["environment"] = ["必须填写运行环境"]
        if not run.output_dataset_id:
            errors["output_dataset"] = ["必须登记结果数据集"]
        return errors
