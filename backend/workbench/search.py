"""Cross-module search: reuse group/owner scopes; only select approved display fields."""
from functools import reduce
from operator import or_

from django.db.models import CharField, Q
from django.db.models.functions import Cast
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from achievements.models import Achievement
from core.permissions import IsActiveMember, scope_finance, scope_group, scope_private
from datasets.models import Dataset
from equipment.models import Equipment
from inventory.models import Consumable
from knowledge.models import Doc
from meetings.models import Meeting
from procurement.models import PurchaseRequest
from projects.models import Project
from reports.models import WeeklyReport
from research.models import Experiment, ProcessingRun
from specimens.models import Specimen

LIMIT = 5
MAX_LENGTH = 100

# Key, label, model, scope, frontend destination, visible title, match fields, optional subtitle.
MODULES = (
    ("projects", "项目", Project, scope_group, "/projects/{id}", "name", ("name",), None),
    ("experiments", "实验记录", Experiment, scope_private, "/experiments/{id}", "title", ("title",), None),
    ("runs", "数据处理", ProcessingRun, scope_private, "/runs/{id}", "title", ("title",), None),
    ("datasets", "数据集", Dataset, scope_private, "/datasets/{id}", "name", ("name",), None),
    ("reports", "周报", WeeklyReport, scope_private, "/reports/{id}", "week_start", ("date_text",), None),
    ("purchases", "采购申请", PurchaseRequest, scope_finance, "/purchases/{id}", "purpose",
     ("purpose", "items__name"), None),
    ("equipment", "设备", Equipment, scope_group, "/equipment/{id}", "name",
     ("name", "code", "model", "category", "location"), "code"),
    ("specimens", "试件", Specimen, scope_group, "/specimens/{id}", "name",
     ("name", "code", "material", "location"), "code"),
    ("consumables", "耗材", Consumable, scope_group, "/consumables?item={id}", "name",
     ("name", "spec", "location"), "spec"),
    ("knowledge", "知识库", Doc, scope_group, "/knowledge?doc={id}", "title", ("title",), None),
    ("meetings", "组会", Meeting, scope_group, "/meetings/{id}", "title", ("title",), None),
    ("achievements", "成果", Achievement, scope_group, "/achievements?item={id}", "title", ("title",), None),
)


class SearchQuery(serializers.Serializer):
    q = serializers.CharField(min_length=2, max_length=MAX_LENGTH, trim_whitespace=True)


class SearchView(APIView):
    permission_classes = [IsActiveMember]

    def get(self, request):
        query = SearchQuery(data=request.query_params)
        query.is_valid(raise_exception=True)
        q = query.validated_data["q"]
        results = []
        for key, label, model, scope, link, title, fields, subtitle in MODULES:
            queryset = scope(model.objects.all(), request.user)
            if model is WeeklyReport:
                queryset = queryset.alias(date_text=Cast("week_start", CharField()))
            matches = reduce(or_, (Q(**{f"{field}__icontains": q}) for field in fields))
            selected = ("pk", title, subtitle) if subtitle else ("pk", title)
            rows = queryset.filter(matches).order_by("-pk").values(*selected).distinct()[:LIMIT]
            items = []
            for row in rows:
                pk = row["pk"]
                target = link.format(id=pk)
                items.append({
                    "id": pk,
                    "title": str(row[title])[:160] if row[title] else f"{label} #{pk}",
                    "subtitle": row[subtitle] if subtitle else "",
                    "link": target,
                })
            if items:
                results.append({"module": key, "label": label, "items": items})
        return Response(results, headers={"Cache-Control": "private, no-store"})
