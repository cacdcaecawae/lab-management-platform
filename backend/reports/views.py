from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from accounts.serializers import UserBriefSerializer
from core.exceptions import Conflict
from core.history import serialize_history
from core.notifications import notify
from core.permissions import IsActiveMember, IsAdvisor, IsOwnerOrReadOnly, scope_private
from datasets.versions import pin_versions

from .models import WeeklyReport
from .queries import current_week_start, missing_students
from .serializers import FeedbackSerializer, ReportQuerySerializer, WeeklyReportSerializer

Status = WeeklyReport.Status
EDITABLE = (Status.DRAFT, Status.NEEDS_REVISION)


def _render_digest_markdown(week_start, reports, missing):
    lines = [
        f"# 周报汇总（{week_start.isoformat()} 这一周）",
        "",
        f"- 已交：{len(reports)} 份",
        f"- 未交：{'、'.join(u.name for u in missing) if missing else '无'}",
        "",
    ]
    if not reports:
        lines.append("本周暂无已提交周报。")
        lines.append("")
        return "\n".join(lines)

    for report in reports:
        lines.extend([
            "---",
            "",
            f"## {report.owner.name}（{report.get_status_display()}）",
            "",
        ])
        for heading, value in (
            ("本周目标", report.goals),
            ("完成工作", report.done),
            ("主要发现与证据", report.findings),
            ("下周计划", report.next_plan),
        ):
            lines.extend([f"### {heading}", "", value.strip() or "（未填写）", ""])

        exps = list(report.experiments.all())
        ds_list = list(report.datasets.all())
        runs = list(report.runs.all())
        if exps or ds_list or runs:
            lines.extend(["### 关联记录", ""])
            for e in exps:
                lines.append(f"- 实验：{e.code} {e.title}")
            for d in ds_list:
                lines.append(f"- 数据集：{d.code} {d.name}")
            for r in runs:
                lines.append(f"- 处理记录：{r.code} {r.title}")
            lines.append("")

        fb_list = list(report.feedback.all())
        if fb_list:
            lines.extend(["### 导师反馈", ""])
            for fb in fb_list:
                verdict = fb.get_verdict_display()
                detail = f"：{fb.content.strip()}" if fb.content.strip() else ""
                lines.append(f"- {fb.author.name}（{verdict}）{detail}")
            lines.append("")

    return "\n".join(lines)


class WeeklyReportViewSet(viewsets.ModelViewSet):
    serializer_class = WeeklyReportSerializer
    permission_classes = [IsActiveMember, IsOwnerOrReadOnly]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    filter_backends = [filters.SearchFilter]
    search_fields = ["owner__name", "goals", "done", "findings", "next_plan"]

    def get_queryset(self):
        qs = scope_private(WeeklyReport.objects.all(), self.request.user)
        if self.action == "list":
            query = ReportQuerySerializer(data=self.request.query_params)
            query.is_valid(raise_exception=True)
            qs = qs.filter(**query.validated_data)
        return qs.select_related("owner").prefetch_related("experiments", "datasets", "runs", "feedback__author")

    def _lock(self):
        """Scope and owner checks as for any detail request (404 / 403), then re-read the row FOR UPDATE
        so concurrent state changes wait for each other. Call inside transaction.atomic()."""
        return WeeklyReport.objects.select_for_update().get(pk=self.get_object().pk)

    def _detail(self, report):
        # Re-read with prefetches: the locked row has none, and feedback may have just been added.
        return Response(self.get_serializer(self.get_queryset().get(pk=report.pk)).data)

    def perform_create(self, serializer):
        try:
            with transaction.atomic():
                serializer.save(owner=self.request.user)
        except IntegrityError:  # unique (owner, week_start); also covers two concurrent creates
            raise Conflict("这一周的周报已经存在。", code="conflict")

    def update(self, request, *args, **kwargs):
        with transaction.atomic():
            report = self._lock()
            if report.status not in EDITABLE:
                raise Conflict("周报已提交，不能修改。", code="invalid_state")
            serializer = self.get_serializer(report, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
        return self._detail(report)

    def destroy(self, request, *args, **kwargs):
        with transaction.atomic():
            report = self._lock()
            if report.status != Status.DRAFT:
                raise Conflict("只能删除草稿。", code="invalid_state")
            report.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        with transaction.atomic():
            report = self._lock()
            if report.status not in EDITABLE:
                raise Conflict("周报已提交，不能重复提交。", code="invalid_state")
            report.status = Status.SUBMITTED
            report.submitted_at = timezone.now()
            report.data_versions = pin_versions(report.cited_datasets())
            report.save()
        return self._detail(report)

    @action(detail=True, methods=["post"], permission_classes=[IsActiveMember, IsAdvisor])
    def feedback(self, request, pk=None):
        with transaction.atomic():
            report = self._lock()
            if report.owner_id == request.user.id:
                raise PermissionDenied("不能反馈自己的周报。")
            if report.status != Status.SUBMITTED:
                raise Conflict("只有已提交的周报可以反馈。", code="invalid_state")
            serializer = FeedbackSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            feedback = serializer.save(report=report, author=request.user)
            report.status = feedback.verdict
            report.save()
            title = "周报需补充" if report.status == Status.NEEDS_REVISION else "周报已阅"
            notify(report.owner.group_id, title, f"/reports/{report.pk}", recipient_ids=[report.owner_id])
        return self._detail(report)

    @action(detail=True)
    def history(self, request, pk=None):
        return Response(serialize_history(self.get_object()))

    @action(detail=False, permission_classes=[IsActiveMember, IsAdvisor])
    def missing(self, request):
        query = ReportQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        week_start = query.validated_data.get("week_start", current_week_start())
        return Response(UserBriefSerializer(missing_students(request.user, week_start), many=True).data)

    def _digest_data(self, request):
        query = ReportQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        week_start = query.validated_data.get("week_start", current_week_start())
        reports = list(
            self.get_queryset()
            .filter(week_start=week_start)
            .exclude(status=Status.DRAFT)
            .order_by("owner__name", "owner_id")
        )
        missing = list(missing_students(request.user, week_start))
        return week_start, reports, missing

    @action(detail=False, permission_classes=[IsActiveMember, IsAdvisor])
    def digest(self, request):
        week_start, reports, missing = self._digest_data(request)
        return Response({
            "week_start": week_start.isoformat(),
            "reports": self.get_serializer(reports, many=True).data,
            "missing": UserBriefSerializer(missing, many=True).data,
        })

    @action(detail=False, url_path="digest/export", permission_classes=[IsActiveMember, IsAdvisor])
    def digest_export(self, request):
        week_start, reports, missing = self._digest_data(request)
        md = _render_digest_markdown(week_start, reports, missing)
        resp = HttpResponse(md, content_type="text/markdown; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="weekly-digest-{week_start.isoformat()}.md"'
        resp["Cache-Control"] = "private, no-store"
        return resp
