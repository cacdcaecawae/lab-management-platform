"""Read-only storage metadata rollups. No storage listings or per-object probes."""
import shutil
from collections import defaultdict
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from django.core.files.storage import FileSystemStorage, default_storage
from django.db.models import Case, Count, DateField, F, Q, Sum, Value, When
from django.db.models.functions import TruncMonth
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import ResearchGroup
from achievements.models import Achievement
from core.permissions import IsActiveMember, IsSupervisor, IsSuperuser, scope_group
from datasets.models import DataFile
from equipment.models import UsageReport
from knowledge.models import DocVersion
from meetings.models import MeetingFile
from procurement.models import Attachment

SHANGHAI = ZoneInfo("Asia/Shanghai")
MODULES = ("raw", "knowledge", "meetings", "procurement", "achievements", "equipment")


def both():
    return {"known_bytes": 0, "unknown_files": 0}


def month_before(month, n):
    index = month.year * 12 + month.month - 1 - n
    year, index = divmod(index, 12)
    return date(year, index + 1, 1)


def month_key(value):
    return value.strftime("%Y-%m")


def mount_info():
    # Django's backend is lazy; isinstance delegates to its wrapped class.
    if not isinstance(default_storage, FileSystemStorage):
        return {"kind": "non_local", "filesystem": None}
    try:
        total, used, free = shutil.disk_usage(default_storage.location)
    except OSError:
        return {"kind": "local", "filesystem": None}
    return {"kind": "local", "filesystem": {"total_bytes": total, "used_bytes": used, "free_bytes": free}}


def source_rows(queryset, group, timestamp, size, cutoff):
    group_expr = F(group) if isinstance(group, str) else group
    # Group older records into one bucket; the total still counts them.
    month = Case(
        When(**{f"{timestamp}__gte": cutoff}, then=TruncMonth(timestamp, tzinfo=SHANGHAI, output_field=DateField())),
        default=Value(None), output_field=DateField(),
    )
    return queryset.order_by().values(group_key=group_expr, month=month).annotate(
        known_bytes=Sum(size, filter=Q(**{f"{size}__gte": 0})),
        known_files=Count("pk", filter=Q(**{f"{size}__gte": 0})),
        file_count=Count("pk"),
    )


def ops_summary():
    current = timezone.localdate(timezone=SHANGHAI).replace(day=1)
    oldest = month_before(current, 11)
    cutoff = timezone.make_aware(datetime.combine(oldest, time.min), SHANGHAI)
    months = [month_key(month_before(current, offset)) for offset in range(11, -1, -1)]
    groups = {
        pk: {"id": pk, "name": name, "modules": {module: both() for module in MODULES}, "months": {key: 0 for key in months}}
        for pk, name in ResearchGroup.objects.order_by("name", "pk").values_list("pk", "name")
    }
    unassigned = {"id": None, "name": "未分配课题组", "modules": {module: both() for module in MODULES},
                  "months": {key: 0 for key in months}}
    sources = (
        ("raw", DataFile.objects.exclude(file=""), "dataset__owner__group_id", "uploaded_at", "size"),
        ("knowledge", DocVersion.objects.exclude(file=""), "doc__group_id", "created_at", "size"),
        ("meetings", MeetingFile.objects.exclude(file=""), "meeting__group_id", "created_at", "size"),
        ("procurement", Attachment.objects.exclude(file=""), Case(
            When(purchase__isnull=False, then=F("purchase__owner__group_id")), default=F("reimbursement__owner__group_id")
        ), "created_at", "size"),
        ("equipment", UsageReport.objects.exclude(photo=""), "booking__equipment__group_id", "reported_at", "photo_size"),
    )
    month_observations = defaultdict(int)
    for module, queryset, group, ts, size in sources:
        for item in source_rows(queryset, group, ts, size, cutoff):
            summary = groups.get(item["group_key"], unassigned)
            bucket = summary["modules"][module]
            bucket["known_bytes"] += item["known_bytes"] or 0
            bucket["unknown_files"] += item["file_count"] - item["known_files"]
            label = month_key(item["month"]) if item["month"] else None
            if label in summary["months"]:
                summary["months"][label] += item["known_bytes"] or 0
                month_observations[label] += item["known_files"]

    # This model records neither the fulltext size nor its upload time. Never probe storage.
    for item in Achievement.objects.exclude(fulltext="").order_by().values("group_id").annotate(n=Count("pk")):
        groups.get(item["group_id"], unassigned)["modules"]["achievements"]["unknown_files"] = item["n"]

    result = list(groups.values())
    if any(value for module in unassigned["modules"].values() for value in module.values()):
        result.append(unassigned)
    for group in result:
        group.update({field: sum(module[field] for module in group["modules"].values()) for field in both()})
    basis = months[-4:-1]
    # A month without any surviving recorded size is not treated as an observed zero.
    projection = None
    if all(month_observations[key] for key in basis):
        annual = sum(group["months"][key] for group in result for key in basis) * 4
        projection = {"basis_months": basis, "annual_retained_known_bytes": annual}
    return {"disk": mount_info(), "groups": result, "month_keys": months, "projection": projection}


class OpsStorageView(APIView):
    permission_classes = [IsSuperuser]

    def get(self, request):
        return Response(ops_summary())


class GroupStorageView(APIView):
    permission_classes = [IsActiveMember, IsSupervisor]

    def get(self, request):
        raw = scope_group(DataFile.objects.exclude(file=""), request.user, group_field="dataset__owner__group").order_by()
        # Show only member identities currently in the authorized group. If a file uploader
        # moved group, count those bytes in a single unattributed bucket.
        member = Case(When(uploaded_by__group_id=request.user.group_id, then=F("uploaded_by_id")), default=Value(None))
        name = Case(When(uploaded_by__group_id=request.user.group_id, then=F("uploaded_by__name")), default=Value(""))
        project = Case(When(dataset__project__group_id=request.user.group_id, then=F("dataset__project_id")), default=Value(None))
        project_name = Case(When(dataset__project__group_id=request.user.group_id, then=F("dataset__project__name")), default=Value(""))
        def rows(key, label, fallback):
            totals = raw.values(key=key, label=label).annotate(
                known_bytes=Sum("size", filter=Q(size__gte=0)), unknown_files=Count("pk", filter=Q(size__lt=0))
            ).order_by("label", "key")
            return [
                {"id": row["key"], "label": row["label"] or fallback,
                 "known_bytes": row["known_bytes"] or 0, "unknown_files": row["unknown_files"]}
                for row in totals
            ]
        return Response({
            "by_member": rows(member, name, "未归属或未命名成员"),
            "by_project": rows(project, project_name, "未归属项目"),
        })
