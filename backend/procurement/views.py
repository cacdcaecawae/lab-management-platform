import re

from django.db import transaction
from django.db.models import BooleanField, Count, Exists, ExpressionWrapper, F, OuterRef, ProtectedError, Q, Sum
from django.db.models.functions import TruncMonth
from django.http import FileResponse, HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import content_disposition_header
from openpyxl import Workbook
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.filters import SearchFilter
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from accounts.models import User
from core import mail
from core.exceptions import Conflict, MailFailed
from core.export import xlsx_bytes
from core.files import delete_on_commit
from core.history import serialize_history
from core.permissions import IsActiveMember, IsManager, IsSupervisor, is_manager, scope_group, scope_private

from .mail import notify, send_finance_reminder
from .models import Approval, Attachment, Fund, PurchaseRequest, Reimbursement
from .serializers import (
    AdvanceSerializer,
    AttachmentSerializer,
    FinanceEmailSerializer,
    FundSerializer,
    PurchaseDetailSerializer,
    PurchaseSerializer,
    ReimbursementSerializer,
    ReviewSerializer,
)

S = PurchaseRequest.Status
R = Reimbursement.Status
EDIT_BLOCKED = {
    S.PENDING_INITIAL: "审批中的申请不能修改，请先撤回",
    S.PENDING_FINAL: "审批中的申请不能修改，请先撤回",
    S.ARRIVED: "已到货的申请不能修改",
}
STAGE_OF = {S.PENDING_INITIAL: Approval.Stage.INITIAL, S.PENDING_FINAL: Approval.Stage.FINAL}


def first_review(owner):
    """A manager's own request skips the initial review (managers do initial reviews)."""
    return S.PENDING_FINAL if owner.role == User.Role.MANAGER else S.PENDING_INITIAL


def returned_flag():
    """True for a draft whose latest submission was sent back (a withdrawal is not a return)."""
    sent_back = Approval.objects.filter(
        request=OuterRef("pk"), verdict=Approval.Verdict.RETURN, created_at__gte=OuterRef("submitted_at")
    )
    return ExpressionWrapper(Q(status=S.DRAFT) & Exists(sent_back), output_field=BooleanField())


def awaiting_review(purchases, user):
    """The part of an (already scoped) queryset that waits for `user`'s review."""
    stage_status = {User.Role.MANAGER: S.PENDING_INITIAL, User.Role.ADVISOR: S.PENDING_FINAL}.get(user.role)
    if not stage_status:
        return purchases.none()
    return purchases.filter(status=stage_status).exclude(owner=user)


def item_lines(items):
    # What an approval covers: name, quantity, unit price. Spec, link and fund edits do not need a new approval.
    return [f"{i['name']} {i['quantity']}×{i['unit_price']:.2f}" for i in items]


def delete_files_on_commit(attachments):
    delete_on_commit([a.file for a in attachments])


def submission_errors(purchase):
    """What keeps a request from going to review, as field errors; empty when it may."""
    errors = {}
    if not purchase.purpose.strip():
        errors["purpose"] = ["提交前必须填写用途"]
    if not purchase.fund_id:
        errors["fund_id"] = ["提交前必须选择经费来源"]
    elif not purchase.fund.active:
        errors["fund_id"] = ["该经费来源已停用，请换一个"]
    if not purchase.items.exists():
        errors["items"] = ["至少需要 1 条明细"]
    elif purchase.total <= 0:
        errors["items"] = ["合计必须大于 0"]
    return errors


def save_attachment(request, **parent):
    serializer = AttachmentSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save(uploaded_by=request.user, **parent)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


class FundViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet
):
    """Group-wide read (forms pick a fund); only managers create and edit. No delete: a fund is stopped (active=false)."""

    http_method_names = ["get", "post", "patch", "head", "options"]
    serializer_class = FundSerializer
    filter_backends = [SearchFilter]
    search_fields = ["code", "name"]

    def get_permissions(self):
        if self.action in ("create", "partial_update"):
            return [IsActiveMember(), IsManager()]
        return [IsActiveMember()]

    def get_queryset(self):
        funds = scope_group(Fund.objects.select_related("owner"), self.request.user)
        if self.action == "list" and self.request.query_params.get("active") == "1":
            funds = funds.filter(active=True)
        return funds

    def perform_create(self, serializer):
        serializer.save(group=self.request.user.group)


class PurchaseViewSet(viewsets.ModelViewSet):
    """Private scope: the applicant, and the managers and advisors of the applicant's group.
    Every state change locks the row first, then checks the state (see the proposal note's concurrency rules)."""

    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    filter_backends = [SearchFilter]
    search_fields = ["purpose", "items__name", "owner__name"]

    def get_serializer_class(self):
        return PurchaseSerializer if self.action == "list" else PurchaseDetailSerializer

    def get_queryset(self):
        user = self.request.user
        purchases = (
            scope_private(PurchaseRequest.objects.select_related("owner", "fund"), user)
            .prefetch_related("items")
            .annotate(returned=returned_flag())
        )
        if self.action != "list":  # list filters must not turn detail URLs into 404s
            return purchases.prefetch_related("approvals__reviewer", "attachments__uploaded_by")
        params = self.request.query_params
        if params.get("status"):
            if params["status"] not in S.values:
                return purchases.none()
            purchases = purchases.filter(status=params["status"])
        if params.get("mine") == "1":
            purchases = purchases.filter(owner=user)
        if params.get("todo") == "1":
            purchases = awaiting_review(purchases, user)
        return purchases

    def lock(self):
        # get_object() applies the scope (404); lock separately so FOR UPDATE stays on this one row.
        return PurchaseRequest.objects.select_for_update().get(pk=self.get_object().pk)

    def respond(self, pk, code=status.HTTP_200_OK):
        return Response(self.get_serializer(self.get_queryset().get(pk=pk)).data, status=code)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            self.perform_create(serializer)
        return self.respond(serializer.instance.pk, status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        user = request.user
        with transaction.atomic():
            purchase = self.lock()
            mine = purchase.owner_id == user.id
            if not (mine or (is_manager(user) and purchase.status in (S.APPROVED, S.PURCHASED))):
                raise PermissionDenied("只能修改自己的申请")
            if purchase.status in EDIT_BLOCKED:
                raise Conflict(EDIT_BLOCKED[purchase.status], code="invalid_state")
            serializer = self.get_serializer(purchase, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            new_items = serializer.validated_data.get("items")
            before = item_lines(purchase.items.values("name", "quantity", "unit_price"))
            after = before if new_items is None else item_lines(new_items)
            reset = purchase.status != S.DRAFT and after != before
            if reset:  # what was approved is no longer what will be bought
                purchase.status = first_review(purchase.owner)
                purchase.submitted_at = timezone.now()
                purchase._change_reason = f"{user.display_name} 修改了明细，重新审批：{'；'.join(before)} → {'；'.join(after)}"
            serializer.save()
            if reset:
                # Going back to review is a new submission: the same checks apply (no empty or 0-yuan request).
                if errors := submission_errors(purchase):
                    raise ValidationError(errors)  # inside the transaction: nothing of the edit is kept
                transaction.on_commit(lambda: notify(purchase.pk))
        return self.respond(purchase.pk)

    def destroy(self, request, *args, **kwargs):
        with transaction.atomic():
            purchase = self.lock()
            if purchase.owner_id != request.user.id:
                raise PermissionDenied("只能删除自己的申请")
            if purchase.status != S.DRAFT or purchase.submitted_at:
                raise Conflict("提交过的申请不能删除，留作记录", code="invalid_state")
            delete_files_on_commit(purchase.attachments.all())
            try:
                purchase.delete()
            except ProtectedError as exc:  # a reimbursement may point at its owner's draft
                codes = "、".join(getattr(obj, "code", str(obj)) for obj in exc.protected_objects)
                raise Conflict(f"报销 {codes} 关联了这张草稿，先在报销里取消关联再删除", code="in_use")
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        with transaction.atomic():
            purchase = self.lock()
            if purchase.owner_id != request.user.id:
                raise PermissionDenied("只能提交自己的申请")
            if purchase.status != S.DRAFT:
                raise Conflict("只有草稿可以提交", code="invalid_state")
            if errors := submission_errors(purchase):
                raise ValidationError(errors)
            purchase.status = first_review(purchase.owner)
            purchase.submitted_at = timezone.now()
            purchase.save()
            transaction.on_commit(lambda: notify(purchase.pk))
        return self.respond(purchase.pk)

    @action(detail=True, methods=["post"])
    def withdraw(self, request, pk=None):
        with transaction.atomic():
            purchase = self.lock()
            if purchase.owner_id != request.user.id:
                raise PermissionDenied("只能撤回自己的申请")
            if purchase.status not in STAGE_OF:
                raise Conflict("只有审批中的申请可以撤回", code="invalid_state")
            purchase.status = S.DRAFT
            purchase._change_reason = "申请人撤回"
            purchase.save()
        return self.respond(purchase.pk)

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        user = request.user
        body = ReviewSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        verdict, comment = body.validated_data["verdict"], body.validated_data["comment"]
        with transaction.atomic():
            purchase = self.lock()
            if purchase.owner_id == user.id:
                raise PermissionDenied("不能审批自己的申请")
            if not user.is_supervisor:
                raise PermissionDenied("只有管理员和导师可以审批")
            # A decision is about what the reviewer saw. If the state or the total moved since (a withdrawal, an edit,
            # another reviewer), it does not apply to the current request.
            if purchase.status != body.validated_data["status_seen"] or purchase.total != body.validated_data["total_seen"]:
                raise Conflict("单据已变化（状态或金额与你看到的不同），请刷新后再审", code="stale")
            stage = STAGE_OF.get(purchase.status)
            if not stage:
                raise Conflict(f"当前为“{purchase.get_status_display()}”，不需要审批", code="invalid_state")
            if stage == Approval.Stage.INITIAL and user.role != User.Role.MANAGER:
                raise PermissionDenied("初审只能由管理员完成")
            if stage == Approval.Stage.FINAL and user.role != User.Role.ADVISOR:
                raise PermissionDenied("终审只能由导师完成")
            Approval.objects.create(
                request=purchase, stage=stage, reviewer=user, verdict=verdict, comment=comment, total=purchase.total
            )
            if verdict == Approval.Verdict.RETURN:
                purchase.status = S.DRAFT
            elif stage == Approval.Stage.INITIAL and purchase.owner.role != User.Role.ADVISOR:
                purchase.status = S.PENDING_FINAL
            else:  # final review, or an advisor's own request after the initial review
                purchase.status = S.APPROVED
            purchase._change_reason = f"{Approval.Stage(stage).label}{Approval.Verdict(verdict).label}：{comment}".rstrip("：")
            purchase.save()
            transaction.on_commit(lambda: notify(purchase.pk, comment))
        return self.respond(purchase.pk)

    def mark(self, from_status, to_status):
        if not is_manager(self.request.user):
            raise PermissionDenied("只有管理员可以登记采购和到货")
        with transaction.atomic():
            purchase = self.lock()
            if purchase.status != from_status:
                raise Conflict(f"当前为“{purchase.get_status_display()}”，不能标记为“{to_status.label}”", code="invalid_state")
            purchase.status = to_status
            purchase.save()
            if to_status == S.ARRIVED:
                transaction.on_commit(lambda: notify(purchase.pk))
        return self.respond(purchase.pk)

    @action(detail=True, methods=["post"])
    def purchased(self, request, pk=None):
        return self.mark(S.APPROVED, S.PURCHASED)

    @action(detail=True, methods=["post"])
    def arrived(self, request, pk=None):
        return self.mark(S.PURCHASED, S.ARRIVED)

    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser])
    def attachments(self, request, pk=None):
        purchase = self.get_object()
        if not (purchase.owner_id == request.user.id or is_manager(request.user)):
            raise PermissionDenied("只有申请人和管理员可以上传附件")
        return save_attachment(request, purchase=purchase)

    @action(detail=True)
    def history(self, request, pk=None):
        return Response(serialize_history(self.get_object()))


class AttachmentViewSet(mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """Download and delete only; uploads go through the purchase or reimbursement they belong to."""

    def get_queryset(self):
        user = self.request.user
        purchases = scope_private(PurchaseRequest.objects.all(), user)
        reimbursements = scope_private(Reimbursement.objects.all(), user)
        return Attachment.objects.filter(Q(purchase__in=purchases) | Q(reimbursement__in=reimbursements))

    @action(detail=True)
    def file(self, request, pk=None):
        attachment = self.get_object()
        return FileResponse(attachment.file.open("rb"), filename=attachment.name)

    def destroy(self, request, *args, **kwargs):
        attachment = self.get_object()
        if not (attachment.uploaded_by_id == request.user.id or is_manager(request.user)):
            raise PermissionDenied("只有上传人和管理员可以删除附件")
        with transaction.atomic():
            # Lock the parent: an invoice must not disappear while the reimbursement is being handed to finance.
            if attachment.purchase_id:
                parent = PurchaseRequest.objects.select_for_update().get(pk=attachment.purchase_id)
                if parent.status in STAGE_OF:
                    raise Conflict("审批中的申请不能删除附件，请先撤回", code="invalid_state")
                # After a review only what no reviewer has seen: files uploaded since the latest review.
                if parent.status != S.DRAFT and parent.approvals.filter(created_at__gte=attachment.created_at).exists():
                    raise Conflict("审批人已经看过这份附件，不能删除", code="invalid_state")
            else:
                parent = Reimbursement.objects.select_for_update().get(pk=attachment.reimbursement_id)
                if parent.status != R.PENDING:
                    raise Conflict("已交财务的报销不能删除附件", code="invalid_state")
            delete_files_on_commit([attachment])
            attachment.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


STATS_BY = {"fund": "经费来源", "category": "类别", "owner": "人员", "month": "月份"}


def filter_reimbursements(queryset, params):
    """Filters shared by the list, the statistics and the export, so their totals agree."""
    for name, choices in (("status", R.values), ("category", Reimbursement.Category.values)):
        if params.get(name):
            if params[name] not in choices:
                raise ValidationError({name: [f"可选 {', '.join(choices)}"]})
            queryset = queryset.filter(**{name: params[name]})
    for name in ("fund", "owner"):
        if params.get(name):
            if not params[name].isdigit():
                raise ValidationError({name: ["必须是整数"]})
            queryset = queryset.filter(**{f"{name}_id": int(params[name])})
    if params.get("month"):
        match = re.fullmatch(r"(\d{4})-(\d{2})", params["month"])
        if not match:
            raise ValidationError({"month": ["格式为 YYYY-MM"]})
        queryset = queryset.filter(occurred_on__year=int(match[1]), occurred_on__month=int(match[2]))
    for name, lookup in (("from", "occurred_on__gte"), ("to", "occurred_on__lte")):
        if params.get(name):
            try:
                day = parse_date(params[name])
            except ValueError:
                day = None
            if day is None:
                raise ValidationError({name: ["格式为 YYYY-MM-DD"]})
            queryset = queryset.filter(**{lookup: day})
    return queryset


def summarize(queryset, by):
    """[{key, label, count, total}] grouped by `by`, plus the overall count and total, all computed by the database."""
    if by not in STATS_BY:
        raise ValidationError({"by": [f"可选 {', '.join(STATS_BY)}"]})
    column = TruncMonth("occurred_on") if by == "month" else F(by)
    groups = (
        queryset.order_by()
        .values(key=column)
        .annotate(count=Count("id"), total=Sum("amount"))
        .order_by("key" if by == "month" else "-total", "key")
    )
    labels = {}
    if by == "fund":
        labels = {f.id: str(f) for f in Fund.objects.filter(id__in=[g["key"] for g in groups])}
    elif by == "owner":
        labels = {u.id: u.display_name for u in User.objects.filter(id__in=[g["key"] for g in groups])}
    elif by == "category":
        labels = dict(Reimbursement.Category.choices)
    rows = [
        {
            "key": f"{g['key']:%Y-%m}" if by == "month" else g["key"],
            "label": f"{g['key']:%Y-%m}" if by == "month" else labels.get(g["key"], str(g["key"])),
            "count": g["count"],
            "total": g["total"],
        }
        for g in groups
    ]
    overall = queryset.aggregate(count=Count("id"), total=Sum("amount", default=0))
    return rows, overall


def local_day(value):
    return timezone.localtime(value).strftime("%Y-%m-%d") if value else ""


class ReimbursementViewSet(viewsets.ModelViewSet):
    """Private scope. No approval: the owner or a manager moves a record pending -> submitted -> paid; only a manager
    moves it back from submitted to pending. Amounts and the rest are frozen once handed to finance."""

    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    serializer_class = ReimbursementSerializer

    def get_permissions(self):
        if self.action in ("stats", "export"):
            return [IsActiveMember(), IsSupervisor()]
        if self.action in ("remind_finance", "finance_email"):
            return [IsActiveMember(), IsManager()]
        return [IsActiveMember()]

    def scoped(self):
        return scope_private(Reimbursement.objects.all(), self.request.user)

    def get_queryset(self):
        reimbursements = self.scoped().select_related("owner", "fund", "purchase__owner").prefetch_related(
            "attachments__uploaded_by"
        )
        if self.action != "list":
            return reimbursements
        return filter_reimbursements(reimbursements, self.request.query_params)

    def lock(self):
        return Reimbursement.objects.select_for_update().get(pk=self.get_object().pk)

    def check_writer(self, reimbursement):
        if not (reimbursement.owner_id == self.request.user.id or is_manager(self.request.user)):
            raise PermissionDenied("只能修改自己的报销")

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def update(self, request, *args, **kwargs):
        with transaction.atomic():
            reimbursement = self.lock()
            self.check_writer(reimbursement)
            if reimbursement.status != R.PENDING:
                raise Conflict("已交财务的报销不能修改，请管理员先退回“待提交”", code="invalid_state")
            serializer = self.get_serializer(reimbursement, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
        return Response(self.get_serializer(self.get_queryset().get(pk=reimbursement.pk)).data)

    def destroy(self, request, *args, **kwargs):
        with transaction.atomic():
            reimbursement = self.lock()
            self.check_writer(reimbursement)
            if reimbursement.status != R.PENDING:
                raise Conflict("已交财务的报销不能删除", code="invalid_state")
            delete_files_on_commit(reimbursement.attachments.all())
            reimbursement.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def advance(self, request, pk=None):
        target = AdvanceSerializer(data=request.data)
        target.is_valid(raise_exception=True)
        target = target.validated_data["status"]
        with transaction.atomic():
            reimbursement = self.lock()
            self.check_writer(reimbursement)
            current = reimbursement.status
            if (current, target) not in {(R.PENDING, R.SUBMITTED), (R.SUBMITTED, R.PAID), (R.SUBMITTED, R.PENDING)}:
                raise Conflict(f"不能从“{R(current).label}”改为“{R(target).label}”", code="invalid_state")
            if target == R.PENDING and not is_manager(request.user):
                raise PermissionDenied("只有管理员可以退回")
            if target == R.SUBMITTED and not reimbursement.attachments.filter(kind=Attachment.Kind.INVOICE).exists():
                raise ValidationError({"attachments": ["交财务前请先上传发票"]})
            reimbursement.status = target
            if target == R.SUBMITTED:
                reimbursement.submitted_at = timezone.now()
            elif target == R.PAID:
                reimbursement.paid_at = timezone.now()
            else:
                reimbursement.submitted_at = None
                reimbursement._change_reason = f"{request.user.display_name} 退回待提交"
            reimbursement.save()
        return Response(self.get_serializer(self.get_queryset().get(pk=reimbursement.pk)).data)

    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser])
    def attachments(self, request, pk=None):
        reimbursement = self.get_object()
        self.check_writer(reimbursement)
        with transaction.atomic():
            # Locked like advance(): no file slips in while the reimbursement is handed to finance.
            locked = Reimbursement.objects.select_for_update().get(pk=reimbursement.pk)
            if locked.status != R.PENDING:
                raise Conflict("已交财务的报销不能再上传附件；需要补充请管理员先退回“待提交”", code="invalid_state")
            return save_attachment(request, reimbursement=locked)

    @action(detail=True)
    def history(self, request, pk=None):
        return Response(serialize_history(self.get_object()))

    @action(detail=False)
    def stats(self, request):
        by = request.query_params.get("by", "category")
        rows, overall = summarize(filter_reimbursements(self.scoped(), request.query_params), by)
        # Amounts as "123.40" strings, like the serializers' DecimalField.
        return Response(
            {
                "by": by,
                "rows": [{**row, "total": f"{row['total']:.2f}"} for row in rows],
                "count": overall["count"],
                "total": f"{overall['total']:.2f}",
            }
        )

    @action(detail=False)
    def export(self, request):
        by = request.query_params.get("by", "category")
        reimbursements = filter_reimbursements(self.scoped(), request.query_params)
        rows, overall = summarize(reimbursements, by)
        book = Workbook()
        summary = book.active
        summary.title = "汇总"
        summary.append([STATS_BY[by], "笔数", "金额（元）"])
        for row in rows:
            summary.append([row["label"], row["count"], row["total"]])
        summary.append(["合计", overall["count"], overall["total"]])
        details = book.create_sheet("明细")
        details.append(["编号", "报销人", "经费号", "经费名称", "类别", "金额（元）", "发生日期", "状态", "交财务", "到账", "关联采购", "说明"])
        for r in reimbursements.select_related("owner", "fund", "purchase").order_by("occurred_on", "id"):
            details.append([
                r.code, r.owner.display_name, r.fund.code, r.fund.name, r.get_category_display(), r.amount, r.occurred_on,
                r.get_status_display(), local_day(r.submitted_at), local_day(r.paid_at),
                r.purchase.code if r.purchase else "", r.description,
            ])
        for sheet, column in ((summary, "C"), (details, "F")):
            for cell in sheet[column][1:]:
                cell.number_format = "0.00"
        for cell in details["G"][1:]:
            cell.number_format = "yyyy-mm-dd"
        response = HttpResponse(
            xlsx_bytes(book), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        filename = f"报销统计-{timezone.localdate():%Y%m%d}.xlsx"
        response["Content-Disposition"] = content_disposition_header(as_attachment=True, filename=filename)
        return response

    @action(detail=False, methods=["post"], url_path="remind-finance")
    def remind_finance(self, request):
        group = request.user.group
        if not group.finance_email:
            raise Conflict("课题组还没有设置财务邮箱，请先点“财务邮箱”填写", code="not_configured")
        if not mail.enabled():
            raise Conflict("平台还没有启用邮件，请联系运维在“系统管理 → 邮件”里设置", code="not_configured")
        try:
            sent = send_finance_reminder(group)
        except Exception as exc:
            raise MailFailed(f"邮件发送失败：{mail.describe(exc)}") from exc
        return Response({"sent": sent, "to": group.finance_email})

    @action(detail=False, methods=["get", "patch"], url_path="finance-email")
    def finance_email(self, request):
        """The group's finance mailbox: managers know who the finance contact is better than ops does."""
        group = request.user.group
        if request.method == "PATCH":
            serializer = FinanceEmailSerializer(group, data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save()
        return Response(FinanceEmailSerializer(group).data)
