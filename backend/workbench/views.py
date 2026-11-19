from datetime import timedelta

from django.db.models import F, Max, Sum
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.serializers import UserBriefSerializer
from core.permissions import is_manager, is_supervisor, scope_group, scope_private
from equipment.models import Booking, Equipment
from equipment.serializers import BookingSerializer, EquipmentBriefSerializer
from inventory.models import Consumable
from inventory.serializers import ConsumableSerializer
from meetings.models import ActionItem
from meetings.serializers import MyActionItemSerializer
from projects.models import Task
from projects.task_board import WorkbenchTaskSerializer, board_tasks
from procurement.models import PurchaseRequest
from procurement.queries import awaiting_review, returned_flag
from procurement.serializers import PurchaseSerializer
from reports.models import WeeklyReport
from reports.queries import current_week_start, missing_students
from reports.serializers import WeeklyReportBriefSerializer
from research.models import Experiment, RecordStatus
from research.serializers import ExperimentBriefSerializer

LIMIT = 20  # the workbench shows the most recent items only; full lists live on each page
UNREPORTED_DAYS = timedelta(days=14)  # older unreported bookings are no longer worth a reminder


class DashboardView(APIView):
    def get(self, request):
        user = request.user
        now = timezone.now()
        week_start = current_week_start()
        mine = WeeklyReport.objects.filter(owner=user).select_related("owner")
        current = mine.filter(week_start=week_start).first()
        bookings = Booking.objects.filter(user=user, cancelled_at__isnull=True).select_related("equipment", "user", "project", "report")
        purchases = (
            scope_private(PurchaseRequest.objects.select_related("owner", "fund"), user)
            .prefetch_related("items")
            .annotate(returned=returned_flag())
        )
        data = {
            "my": {
                "tasks": WorkbenchTaskSerializer(
                    board_tasks(scope_group(Task.objects.filter(assignee=user), user, "project__group_id"))
                    .filter(assignee_current=True).exclude(status=Task.Status.DONE).select_related("project")[:LIMIT],
                    many=True,
                ).data,
                "reports_needing_revision": WeeklyReportBriefSerializer(
                    mine.filter(status=WeeklyReport.Status.NEEDS_REVISION)[:LIMIT], many=True
                ).data,
                "draft_experiments": ExperimentBriefSerializer(
                    Experiment.objects.filter(owner=user, status=RecordStatus.DRAFT).order_by("-updated_at")[:LIMIT], many=True
                ).data,
                "current_week_report": WeeklyReportBriefSerializer(current).data if current else None,
                # current and future bookings, soonest first
                "upcoming_bookings": BookingSerializer(bookings.filter(end_at__gt=now).order_by("start_at")[:LIMIT], many=True).data,
                # use bookings that ended in the last UNREPORTED_DAYS and still need a usage report
                "unreported_bookings": BookingSerializer(
                    bookings.filter(
                        kind=Booking.Kind.USE, end_at__lte=now, end_at__gt=now - UNREPORTED_DAYS, report__isnull=True
                    ).order_by("-start_at")[:LIMIT],
                    many=True,
                ).data,
                "returned_purchases": PurchaseSerializer(
                    purchases.filter(owner=user, returned=True).order_by("-updated_at")[:LIMIT], many=True
                ).data,
                # open action items from group meetings, the most urgent first (no due date last)
                "action_items": MyActionItemSerializer(
                    ActionItem.objects.filter(owner=user, done_at__isnull=True, meeting__group_id=user.group_id)
                    .select_related("owner", "meeting")
                    .order_by(F("due_date").asc(nulls_last=True), "id")[:LIMIT],
                    many=True,
                ).data,
            },
            "supervisor": None,
            "manager": None,
        }
        if is_supervisor(user):
            pending = scope_private(WeeklyReport.objects.filter(status=WeeklyReport.Status.SUBMITTED), user)
            data["supervisor"] = {
                "week_start": week_start,
                "missing_reports": UserBriefSerializer(missing_students(user, week_start), many=True).data,
                "pending_reviews": WeeklyReportBriefSerializer(
                    pending.select_related("owner").order_by("submitted_at")[:LIMIT], many=True
                ).data,
                # managers: waiting for the initial review; advisors: for the final review
                "purchases_to_review": PurchaseSerializer(
                    awaiting_review(purchases, user).order_by("submitted_at")[:LIMIT], many=True
                ).data,
            }
        if is_manager(user):
            to_check = scope_group(Equipment.objects.filter(status=Equipment.Status.NEEDS_CHECK), user)
            low_stock = (
                scope_group(Consumable.objects.all(), user)
                .annotate(stock=Sum("txns__quantity", default=0), stock_version=Max("txns__id", default=0))
                .filter(stock__lt=F("safety_stock"))
                .order_by("name", "spec", "id")
            )
            data["manager"] = {
                "equipment_to_check": EquipmentBriefSerializer(to_check.order_by("code")[:LIMIT], many=True).data,
                "low_stock": ConsumableSerializer(low_stock[:LIMIT], many=True).data,
            }
        return Response(data)
