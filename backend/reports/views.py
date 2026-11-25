from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Prefetch, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from accounts.serializers import UserBriefSerializer
from core import mail
from core.exceptions import Conflict
from core.files import checked_upload, delete_on_commit, download
from core.filters import Ordering, Search
from core.history import serialize_history
from core.models import Notification
from core.notifications import notify
from core.permissions import IsActiveMember, IsAdvisor, IsOwnerOrReadOnly, scope_private
from datasets.versions import pin_versions
from research.models import Experiment, ProcessingRun
from research.serializers import ExperimentBriefSerializer, RunBriefSerializer

from .models import ReportFile, WeeklyReport
from .queries import current_week_start, missing_students
from .serializers import FeedbackSerializer, ReportFileSerializer, ReportQuerySerializer, WeeklyReportSerializer

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
    filter_backends = [Search, Ordering]
    search_fields = ["owner__name", "goals", "done", "findings", "next_plan"]
    ordering_fields = ["week_start", "submitted_at"]

    def get_queryset(self):
        qs = scope_private(WeeklyReport.objects.all(), self.request.user)
        if self.action == "list":
            query = ReportQuerySerializer(data=self.request.query_params)
            query.is_valid(raise_exception=True)
            qs = qs.filter(**query.validated_data)
        return qs.select_related("owner").prefetch_related(
            "experiments", "datasets", "runs", "feedback__author",
            Prefetch("files", ReportFile.objects.select_related("uploaded_by")),
        )

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
            # read after the lock: an upload that finished just before is included
            delete_on_commit([f.file for f in ReportFile.objects.filter(report=report)])
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
            notify(report.owner.group_id, "有新的周报待反馈", f"/reports/{report.pk}", role="advisor",
                   exclude_ids=[report.owner_id], body=f"{report.owner.display_name} · {report.week_start} 这一周")
        return self._detail(report)

    @action(detail=True, methods=["post"])
    def withdraw(self, request, pk=None):
        """The owner takes a report back before an advisor has looked at it, to change it: it returns to where it was
        before that submit, 需补充 when it had been sent back (still handed in, its feedback kept), else 草稿."""
        with transaction.atomic():
            report = self._lock()
            if report.status != Status.SUBMITTED:
                raise Conflict("只有导师尚未批阅的周报可以撤回。", code="invalid_state")
            revised = report.feedback.exists()
            report.status = Status.NEEDS_REVISION if revised else Status.DRAFT
            if not revised:
                report.submitted_at = None
            report.data_versions = {}  # the next submit pins again
            report._change_reason = "本人撤回修改"
            report.save()
        return self._detail(report)

    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser])
    def files(self, request, pk=None):
        """An image or file of the week's work: the owner, while the report can be edited."""
        report = self.get_object()
        uploaded, name = checked_upload(request)
        report_file = ReportFile(report=report, name=name, size=uploaded.size, uploaded_by=request.user)
        report_file.file.save(name, uploaded, save=False)  # written before the lock: a big file must not hold it
        try:
            with transaction.atomic():
                if self._lock().status not in EDITABLE:  # a report deleted meanwhile is a 404
                    raise Conflict("周报已提交，不能再添加附件。", code="invalid_state")
                report_file.save()
        except Exception:
            report_file.file.delete(save=False)
            raise
        return Response(ReportFileSerializer(report_file).data, status=status.HTTP_201_CREATED)

    @action(detail=False, url_path="week-records")
    def week_records(self, request):
        """The requester's own experiments and processing runs created or submitted in that week (Monday to Sunday,
        local dates): what 一键带入本周记录 ticks."""
        query = ReportQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        start = query.validated_data.get("week_start", current_week_start())
        week = (start, start + timedelta(days=6))

        def records(model):
            in_week = Q(created_at__date__range=week) | Q(submitted_at__date__range=week)
            return model.objects.filter(in_week, owner=request.user).order_by("created_at", "id")

        return Response({
            "experiments": ExperimentBriefSerializer(records(Experiment), many=True).data,
            "runs": RunBriefSerializer(records(ProcessingRun), many=True).data,
        })

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

    @action(detail=False, methods=["post"], url_path="remind-missing", permission_classes=[IsActiveMember, IsAdvisor])
    def remind_missing(self, request):
        """Remind the students who have not handed in that week's report: a notification each, and one mail (Bcc) when
        mail is on. At most once a day per student and week, so a second click does not nag."""
        query = ReportQuerySerializer(data=request.data)
        query.is_valid(raise_exception=True)
        week_start = query.validated_data.get("week_start", current_week_start())
        title = f"请提交 {week_start} 这一周的周报"
        missing = list(missing_students(request.user, week_start))
        # shortcut: two advisors clicking in the same instant may both remind; keep a per-week record if that matters.
        reminded = set(
            Notification.objects.filter(recipient__in=missing, title=title, created_at__date=timezone.localdate())
            .values_list("recipient_id", flat=True)
        )
        fresh = [user for user in missing if user.pk not in reminded]
        with transaction.atomic():
            notify(request.user.group_id, title, "/reports", recipient_ids=[user.pk for user in fresh])
        emails = [user.email for user in fresh if user.email]
        body = f"{request.user.display_name} 提醒你提交 {week_start} 这一周的周报。请登录 Phase，在“周报”里填写并提交。"
        mail.send_quietly(f"[周报] {title}", body, emails, "周报催交", bcc=True)
        return Response({"reminded": len(fresh), "already": len(reminded)})

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


class ReportFileViewSet(mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """Download and delete only; uploads go through the report. Read as the report is; deleted by its owner while the
    report can be edited."""

    def get_queryset(self):
        return scope_private(ReportFile.objects.all(), self.request.user, owner_field="report__owner")

    @action(detail=True)
    def file(self, request, pk=None):
        report_file = self.get_object()
        return download(report_file.file, report_file.name)

    def destroy(self, request, *args, **kwargs):
        report_file = self.get_object()
        if report_file.uploaded_by_id != request.user.id:  # the owner: only they upload to their report
            raise PermissionDenied("只能删除自己周报的附件。")
        with transaction.atomic():
            report = get_object_or_404(WeeklyReport.objects.select_for_update(), pk=report_file.report_id)
            if report.status not in EDITABLE:
                raise Conflict("周报已提交，附件不能删除。", code="invalid_state")
            delete_on_commit([report_file.file])
            report_file.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
