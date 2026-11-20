from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db.models import Case, Count, DurationField, ExpressionWrapper, F, Q, Sum, Value, When
from django.db.models.functions import Greatest, Least
from django.http import HttpResponse
from django.urls import path
from openpyxl import Workbook
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from core.export import xlsx_bytes
from core.permissions import IsActiveMember, IsSupervisor, scope_group

from .models import Booking, Equipment, UsageReport

SHANGHAI = ZoneInfo("Asia/Shanghai")
DIMENSIONS = {
    "equipment": ("equipment_id", "equipment__code", "equipment__name"),
}


class StatsQuery(serializers.Serializer):
    from_date = serializers.DateField()
    to_date = serializers.DateField()
    by = serializers.ChoiceField(choices=("equipment", "user", "project", "month"), default="equipment")

    def validate(self, attrs):
        if not 0 < (attrs["to_date"] - attrs["from_date"]).days <= 366:
            raise serializers.ValidationError({"to_date": "结束日期须晚于开始日期，且最多相隔 366 天"})
        return attrs


def midnight(day):
    return datetime.combine(day, time.min, SHANGHAI)


def metrics(low, high, once=None):
    """Clip and aggregate in PostgreSQL; month counts are assigned only once."""
    duration = ExpressionWrapper(Least(F("end_at"), high) - Greatest(F("start_at"), low), output_field=DurationField())
    counted = Q() if once is None else Q(start_at__gte=once)
    return {
        "booked": Sum(duration),
        "reported": Sum(duration, filter=Q(report__isnull=False)),
        "bookings": Count("pk", filter=counted),
        "abnormal": Count("pk", filter=counted & Q(report__condition=UsageReport.Condition.ABNORMAL)),
    }


def row(key, label, aggregate):
    return {
        "key": {"id": key, "label": label},
        "booked_hours": (aggregate.get("booked") or timedelta()).total_seconds() / 3600,
        "reported_hours": (aggregate.get("reported") or timedelta()).total_seconds() / 3600,
        "bookings": aggregate.get("bookings", 0),
        "abnormal": aggregate.get("abnormal", 0),
    }


def usage_rows(user, first, last, by):
    start, end = midnight(first), midnight(last)
    items = scope_group(Booking.objects.all(), user, group_field="equipment__group").filter(
        kind=Booking.Kind.USE, cancelled_at__isnull=True, start_at__lt=end, end_at__gt=start
    ).order_by()
    if by == "month":
        result = []
        day = first
        while day < last:
            month_end = (date(day.year, day.month + 1, 1) if day.month < 12 else
                         date(day.year + 1, 1, 1) if day.year < 9999 else last)
            low, high = midnight(day), midnight(min(month_end, last))
            bucket = f"{day.year:04d}-{day.month:02d}"
            aggregate = items.filter(start_at__lt=high, end_at__gt=low).aggregate(
                **metrics(low, high, None if day == first else low)
            )
            result.append(row(bucket, bucket, aggregate))
            day = month_end
        return result

    if by == "equipment":
        fields = DIMENSIONS["equipment"]
        groups = items.values(*fields).annotate(**metrics(start, end)).order_by(*fields)
        mapped = {g["equipment_id"]: g for g in groups}
        return [
            row(pk, f"{code} {name}", mapped.get(pk, {}))
            for pk, code, name in scope_group(Equipment.objects.all(), user).order_by("code", "pk").values_list("pk", "code", "name")
        ]

    # Ownership of an old booking is independent of current related-object scope.
    # Bucket foreign associations anonymously without dropping their usage metrics.
    local = {f"{by}__group_id": user.group_id}
    label_field = f"{by}__name"
    grouped = items.annotate(
        related_key=Case(When(**local, then=F(f"{by}_id")), default=Value(None)),
        related_label=Case(When(**local, then=F(label_field)), default=Value("")),
        related_fallback=Case(When(**local, then=F("user__username")), default=Value("")) if by == "user" else Value(""),
    ).values("related_key", "related_label", "related_fallback").annotate(**metrics(start, end)).order_by("related_key")
    fallback = "未归属成员" if by == "user" else "未关联项目"
    return [
        row(g["related_key"], g["related_label"] or g["related_fallback"] or fallback, g)
        for g in grouped
    ]


class EquipmentUsageStatsView(APIView):
    permission_classes = [IsActiveMember, IsSupervisor]
    export = False

    def get(self, request):
        params = request.query_params
        query = StatsQuery(data={
            "from_date": params.get("from"), "to_date": params.get("to"), "by": params.get("by", "equipment"),
        })
        query.is_valid(raise_exception=True)
        first, last, by = (query.validated_data[k] for k in ("from_date", "to_date", "by"))
        rows = usage_rows(request.user, first, last, by)
        if not self.export:
            return Response(rows)
        book = Workbook()
        sheet = book.active
        sheet.title = "设备使用统计"
        sheet.append(["分组", "预约小时", "已登记预约小时", "预约数", "异常数"])
        for item in rows:
            sheet.append([item["key"]["label"], item["booked_hours"], item["reported_hours"], item["bookings"], item["abnormal"]])
        response = HttpResponse(xlsx_bytes(book), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = f'attachment; filename="equipment-usage-{first}_{last}.xlsx"'
        return response


urlpatterns = [
    path("equipment/usage-stats/", EquipmentUsageStatsView.as_view(), name="equipment-usage-stats"),
    path("equipment/usage-stats/export/", EquipmentUsageStatsView.as_view(export=True), name="equipment-usage-export"),
]
