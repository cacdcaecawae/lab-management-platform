import logging
from datetime import timedelta
from pathlib import Path

from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response

from accounts.models import User
from core import mail
from core.exceptions import Conflict
from core.files import download
from core.filters import Ordering, Search, equal
from core.history import serialize_history
from core.notifications import notify
from core.pagination import Pagination
from core.permissions import IsActiveMember, IsManager, is_manager, scope_group

from .models import Booking, Equipment, UsageReport
from .queries import awaiting_report, calibration_within
from .serializers import BookingSerializer, EquipmentSerializer, UsageReportSerializer

logger = logging.getLogger(__name__)


def parse_day(text):
    try:
        return parse_date(text)
    except ValueError:  # 2026-13-45: the right shape, not a date
        return None

RECENT_USAGE = 20
MAX_WINDOW = timedelta(days=62)  # the calendar asks for one week; a month view fits too


def in_use_now():
    now = timezone.now()
    current = Booking.objects.filter(equipment=OuterRef("pk"), cancelled_at__isnull=True, start_at__lte=now, end_at__gt=now)
    return Exists(current)


def parse_time(params, name):
    try:
        value = parse_datetime(params.get(name) or "")
    except ValueError:  # well-formed but impossible, e.g. month 13
        value = None
    if value is None:
        raise ValidationError({name: ["需要 ISO 8601 时间"]})
    return value if timezone.is_aware(value) else timezone.make_aware(value)


def notify_managers(report):
    """Mail the group's managers about an abnormal usage report. Mail is optional: a failure is logged and
    never undoes the report (this runs after the commit)."""
    if not mail.enabled():
        return
    booking = report.booking
    equipment = Equipment.objects.get(pk=booking.equipment_id)
    managers = User.objects.filter(group_id=equipment.group_id, is_manager=True, is_active=True).exclude(email="")
    recipients = list(managers.values_list("email", flat=True))
    body = (
        f"{booking.user.display_name} 使用 {equipment.code} {equipment.name} 后登记了异常：\n\n"
        f"{report.description}\n\n设备当前状态：{equipment.get_status_display()}。请登录 Phase 处理。"
    )
    mail.send_quietly(f"[设备异常] {equipment.code} {equipment.name}", body, recipients, "设备异常通知")


class EquipmentViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Group-wide read; only managers create and edit. No delete: retired equipment gets status=retired."""

    http_method_names = ["get", "post", "patch", "head", "options"]
    serializer_class = EquipmentSerializer
    filter_backends = [Search, Ordering]
    search_fields = ["code", "name", "model", "category", "location"]
    ordering_fields = ["code", "calibration_due"]

    def get_permissions(self):
        if self.action in ("create", "partial_update"):
            return [IsActiveMember(), IsManager()]
        return [IsActiveMember()]

    def get_queryset(self):
        equipment = scope_group(
            Equipment.objects.select_related("custodian", "purchase"), self.request.user
        ).annotate(in_use=in_use_now())
        if self.action != "list":  # list filters must not turn detail URLs into 404s
            return equipment
        params = self.request.query_params
        if value := params.get("calibration_within"):
            try:
                days = int(value)
                if not 0 <= days <= 3650:
                    raise ValueError
            except ValueError:
                raise ValidationError({"calibration_within": ["请输入 0 到 3650 的整数天数。"]}) from None
            equipment = calibration_within(equipment, days).order_by("calibration_due", "id")
        if status_filter := params.get("status"):
            equipment = equipment.filter(status=status_filter) if status_filter in Equipment.Status.values else equipment.none()
        if params.get("idle") == "1":
            equipment = equipment.filter(in_use=False)
        return equal(equipment, params, category="category", location="location", custodian="custodian_id")

    def perform_create(self, serializer):
        serializer.save(group=self.request.user.group)

    def retrieve(self, request, *args, **kwargs):
        equipment = self.get_object()
        usage = (
            equipment.bookings.filter(kind=Booking.Kind.USE, cancelled_at__isnull=True, start_at__lte=timezone.now())
            .select_related("equipment", "user", "project", "report")
            .order_by("-start_at")[:RECENT_USAGE]
        )
        recent = BookingSerializer(usage, many=True, context=self.get_serializer_context()).data
        return Response({**self.get_serializer(equipment).data, "recent_usage": recent})

    @action(detail=True)
    def history(self, request, pk=None):
        return Response(serialize_history(self.get_object()))


class BookingViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    """Group-wide read. Anyone in the group books, first come first served; no edits (cancel and book again)."""

    serializer_class = BookingSerializer
    pagination_class = None  # the list always covers a bounded time window (from / to) and the calendar needs all of it

    def get_queryset(self):
        bookings = scope_group(
            Booking.objects.select_related("equipment", "user", "project", "report"), self.request.user, "equipment__group"
        )
        if self.action != "list":  # every_page has its own filters; details and actions see the group's bookings
            return bookings
        params = self.request.query_params
        start, end = parse_time(params, "from"), parse_time(params, "to")
        if not timedelta(0) < end - start <= MAX_WINDOW:
            raise ValidationError({"to": ["时间范围必须大于 0 且不超过 62 天"]})
        bookings = bookings.filter(cancelled_at__isnull=True, start_at__lt=end, end_at__gt=start)
        if params.get("equipment"):
            try:
                bookings = bookings.filter(equipment_id=int(params["equipment"]))
            except ValueError:
                raise ValidationError({"equipment": ["必须是整数"]}) from None
        if params.get("mine") == "1":
            bookings = bookings.filter(user=self.request.user)
        return bookings

    def perform_create(self, serializer):
        data = serializer.validated_data
        kind = data.get("kind", Booking.Kind.USE)
        if kind == Booking.Kind.MAINTENANCE and not is_manager(self.request.user):
            raise PermissionDenied("只有管理员可以预约维护时段")
        try:
            with transaction.atomic():
                # Locked so a concurrent abnormal report (status -> needs_check) cannot slip in between check and insert.
                equipment = Equipment.objects.select_for_update().get(pk=data["equipment"].pk)
                if kind == Booking.Kind.USE and equipment.status != Equipment.Status.AVAILABLE:
                    raise Conflict(f"设备当前为“{equipment.get_status_display()}”，不能预约", code="invalid_state")
                serializer.save(user=self.request.user, equipment=equipment)
        except IntegrityError:  # the exclusion constraint: another booking overlaps this time
            raise Conflict("该时段已被预约，请换一个时间") from None

    @action(detail=False, url_path="all")
    def every_page(self, request):
        """The bookings page's list view: all bookings, newest first, paged, without the calendar's 62-day window.
        mine=1; pending=1 (ended, no usage report yet: as on the workbench); reportable=1 (also under way);
        equipment=<id>; project=<id>; from / to = YYYY-MM-DD (start date, inclusive, local time)."""
        params = request.query_params
        now = timezone.now()
        bookings = self.get_queryset().filter(cancelled_at__isnull=True)
        if params.get("mine") == "1":
            bookings = bookings.filter(user=request.user)
        if params.get("pending") == "1" or params.get("reportable") == "1":
            bookings = awaiting_report(bookings, now, ongoing=params.get("reportable") == "1")
        bookings = equal(bookings, params, equipment="equipment_id", project="project_id")
        for name, lookup in (("from", "start_at__date__gte"), ("to", "start_at__date__lte")):
            if params.get(name):
                day = parse_day(params[name])
                if day is None:
                    raise ValidationError({name: ["格式为 YYYY-MM-DD"]})
                bookings = bookings.filter(**{lookup: day})
        paginator = Pagination()
        page = paginator.paginate_queryset(bookings.order_by("-start_at", "-id"), request, view=self)
        return paginator.get_paginated_response(self.get_serializer(page, many=True).data)

    @action(detail=True, methods=["post"], url_path="end-now")
    def end_now(self, request, pk=None):
        """End a use booking that is under way: the rest of its time is free for others at once. It only ever gets
        shorter, so it cannot come to overlap another booking (the exclusion constraint still guards the row)."""
        user = request.user
        with transaction.atomic():
            booking = self.lock_booking()
            if booking.user_id != user.id and not is_manager(user):
                raise PermissionDenied("只能提前结束自己的预约")
            now = timezone.now()
            if booking.kind != Booking.Kind.USE:
                raise Conflict("维护时段不能提前结束", code="invalid_state")
            if booking.cancelled_at:
                raise Conflict("预约已取消", code="invalid_state")
            # Once only: ended in its first minute it still runs until start + 1 min, and a second end would overwrite
            # planned_end_at with the already shortened end.
            if booking.planned_end_at or not booking.start_at <= now < booking.end_at:
                raise Conflict("只有正在进行的预约可以提前结束", code="invalid_state")
            # Whole minutes, at least one after the start (the end must stay after it), never later than before.
            end = max(now.replace(second=0, microsecond=0), booking.start_at + timedelta(minutes=1))
            booking.planned_end_at, booking.end_at = booking.end_at, min(end, booking.end_at)
            booking.save(update_fields=["end_at", "planned_end_at"])
        return Response(self.get_serializer(self.get_object()).data)

    def lock_booking(self):
        # get_object() applies the group scope (404); lock separately, FOR UPDATE cannot follow nullable outer joins.
        return Booking.objects.select_for_update().get(pk=self.get_object().pk)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        user = request.user
        with transaction.atomic():
            booking = self.lock_booking()
            if booking.cancelled_at:
                raise Conflict("预约已取消", code="invalid_state")
            if not is_manager(user):
                if booking.user_id != user.id:
                    raise PermissionDenied("只能取消自己的预约")
                if booking.start_at <= timezone.now():
                    raise Conflict("预约已开始，不能取消", code="invalid_state")
            if UsageReport.objects.filter(booking=booking).exists():
                raise Conflict("已登记使用结果的预约不能取消", code="invalid_state")
            booking.cancelled_at = timezone.now()
            booking.save(update_fields=["cancelled_at"])
            if booking.user_id != user.id:
                notify(booking.equipment.group_id, "你的设备预约被管理员取消", "/bookings", recipient_ids=[booking.user_id],
                       body=f"{booking.equipment.code} {booking.equipment.name}，{timezone.localtime(booking.start_at):%m-%d %H:%M} 开始")
        return Response(self.get_serializer(self.get_object()).data)

    @action(detail=True, methods=["post"])
    def report(self, request, pk=None):
        if self.get_object().user_id != request.user.id:
            raise PermissionDenied("只有预约人可以登记使用结果")
        body = UsageReportSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        report = None
        committed = False

        def mark_committed():
            nonlocal committed
            committed = True

        try:
            with transaction.atomic():
                booking = self.lock_booking()
                if booking.kind != Booking.Kind.USE:
                    raise Conflict("维护时段不需要登记使用结果", code="invalid_state")
                if booking.cancelled_at:
                    raise Conflict("预约已取消", code="invalid_state")
                if booking.start_at > timezone.now():
                    raise Conflict("使用开始后才能登记", code="invalid_state")
                if UsageReport.objects.filter(booking=booking).exists():
                    raise Conflict("已经登记过使用结果", code="invalid_state")
                report = UsageReport(booking=booking, **body.validated_data)
                if photo := body.validated_data.get("photo"):
                    report.photo_size = photo.size
                    report.photo_uploaded_at = timezone.now()
                report.save()
                transaction.on_commit(mark_committed)
                if report.condition == UsageReport.Condition.ABNORMAL:
                    equipment = Equipment.objects.select_for_update().get(pk=booking.equipment_id)
                    if equipment.status == Equipment.Status.AVAILABLE:
                        equipment.status = Equipment.Status.NEEDS_CHECK
                        equipment._change_reason = f"{request.user.display_name} 登记使用异常：{report.description}"
                        equipment.save()
                    notify(equipment.group_id, "设备登记使用异常", f"/equipment/{equipment.pk}", role="manager")
                    transaction.on_commit(lambda: notify_managers(report))
        except Exception:
            # FileField writes before the database INSERT. Keep the instance even if save() fails.
            # A post-commit callback failure must never delete a committed report's photo.
            if not committed and report and report.photo and report.photo._committed:
                try:
                    report.photo.delete(save=False)
                except Exception:
                    logger.exception("Failed to clean up rolled-back usage photo %s", report.photo.name)
            raise
        return Response(self.get_serializer(self.get_object()).data, status=status.HTTP_201_CREATED)

    @action(detail=True)
    def photo(self, request, pk=None):
        report = getattr(self.get_object(), "report", None)
        if not (report and report.photo):
            raise NotFound()
        return download(report.photo, Path(report.photo.name).name)
