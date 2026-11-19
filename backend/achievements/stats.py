from django.db.models import Count
from django.db.models.functions import ExtractYear
from django.http import HttpResponse
from django.utils.http import content_disposition_header
from openpyxl import Workbook
from rest_framework import serializers

from core.export import xlsx_bytes

from .models import Achievement
from .queries import filter_status

KINDS = tuple(Achievement.Type.values)


class StatsQuery(serializers.Serializer):
    year_from = serializers.IntegerField(min_value=1, max_value=9999, required=False)
    year_to = serializers.IntegerField(min_value=1, max_value=9999, required=False)
    status = serializers.CharField(max_length=100, default="formal")

    def validate(self, attrs):
        if attrs.get("year_from", 1) > attrs.get("year_to", 9999):
            raise serializers.ValidationError({"year_to": "结束年份不能早于开始年份"})
        return attrs


def counts():
    return {**dict.fromkeys(KINDS, 0), "total": 0}


def tally(bucket, kind, number):
    # Storage choices are validated by serializers; ignore unsupported legacy kinds consistently.
    if kind in KINDS:
        bucket[kind] += number
        bucket["total"] += number


def stats(items, group_id, params):
    query = StatsQuery(data={k: params[k] for k in ("year_from", "year_to", "status") if k in params})
    query.is_valid(raise_exception=True)
    selected = query.validated_data
    items = filter_status(items.order_by(), selected["status"])
    if "year_from" in selected:
        items = items.filter(date__year__gte=selected["year_from"])
    if "year_to" in selected:
        items = items.filter(date__year__lte=selected["year_to"])

    years = {}
    for entry in items.annotate(year=ExtractYear("date")).values("year", "type").annotate(n=Count("pk")).order_by("year"):
        bucket = years.setdefault(entry["year"], {"year": entry["year"], **counts()})
        tally(bucket, entry["type"], entry["n"])
    unique = counts()
    for entry in years.values():
        for kind in KINDS:
            tally(unique, kind, entry[kind])

    members = {}
    member_counts = items.filter(members__group_id=group_id).values("members", "members__name", "members__username", "type").annotate(
        n=Count("pk", distinct=True),
    ).order_by("members__name", "members__username", "members")
    for entry in member_counts:
        pk = entry["members"]
        user = {"id": pk, "name": entry["members__name"] or entry["members__username"]}
        bucket = members.setdefault(pk, {"user": user, **counts()})
        tally(bucket, entry["type"], entry["n"])

    return {"by_year": list(years.values()), "by_member": list(members.values()), "total": unique, "status": selected["status"]}


def export_stats(result):
    book = Workbook()
    header = [Achievement.Type(kind).label for kind in KINDS] + ["合计"]
    for title, key, columns, labels in (
        ("按年统计", "by_year", ("年份",), lambda row: (row["year"],)),
        ("按成员统计", "by_member", ("成员", "成员 ID"),
         lambda row: (row["user"]["name"], str(row["user"]["id"]))),
    ):
        sheet = book.active if key == "by_year" else book.create_sheet()
        sheet.title = title
        sheet.append([*columns, *header])
        for entry in result[key]:
            sheet.append([*labels(entry), *(entry[kind] for kind in KINDS), entry["total"]])
        total = result["total"]
        sheet.append(["全组去重总计", *([None] * (len(columns) - 1)), *(total[kind] for kind in KINDS), total["total"]])
    response = HttpResponse(xlsx_bytes(book), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = content_disposition_header(as_attachment=True, filename="成果统计.xlsx")
    return response
