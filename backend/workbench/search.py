"""Cross-module search: reuse group/owner scopes; only select approved display fields."""
import re
from functools import reduce
from operator import or_

from django.db.models import CharField, Q
from django.db.models.functions import Cast
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from achievements.models import Achievement
from core.filters import code_lookup
from core.permissions import IsActiveMember, is_manager, is_supervisor, scope_finance, scope_group, scope_private
from datasets.models import DataFile, Dataset
from equipment.models import Equipment
from inventory.models import Consumable
from knowledge.models import Doc
from meetings.models import ActionItem, Meeting
from procurement.models import Fund, PurchaseRequest, Reimbursement
from projects.models import Milestone, Project, Task
from reports.models import WeeklyReport
from research.models import Experiment, ProcessingRun
from specimens.models import Specimen

LIMIT = 5
MAX_LENGTH = 100

def scoped(scope, field):
    """A scope helper applied through a relation (a task's project, a file's dataset)."""
    return lambda queryset, user: scope(queryset, user, field)


# Key, label, model, scope, frontend destination (formatted with the row: {id} and any selected field), visible title,
# match fields, optional subtitle. A record code (EX-2026-0012 ...) finds its record exactly: CODES.
MODULES = (
    ("projects", "项目", Project, scope_group, "/projects/{id}", "name", ("name",), None),
    ("tasks", "任务", Task, scoped(scope_group, "project__group"), "/projects/{project_id}?tab=tasks", "title", ("title",), "project__name"),
    ("milestones", "里程碑", Milestone, scoped(scope_group, "project__group"), "/projects/{project_id}?tab=milestones", "title",
     ("title",), "project__name"),
    ("experiments", "实验记录", Experiment, scope_private, "/experiments/{id}", "title", ("title",), None),
    ("runs", "数据处理", ProcessingRun, scope_private, "/runs/{id}", "title", ("title",), None),
    ("datasets", "数据集", Dataset, scope_private, "/datasets/{id}", "name", ("name",), None),
    ("files", "数据文件", DataFile, scoped(scope_private, "dataset__owner"), "/datasets/{dataset_id}", "name", ("name",),
     "dataset__name"),
    ("reports", "周报", WeeklyReport, scope_private, "/reports/{id}", "week_start", ("date_text", "owner__name"), "owner__name"),
    ("purchases", "采购申请", PurchaseRequest, scope_finance, "/purchases/{id}", "purpose",
     ("purpose", "items__name"), None),
    ("reimbursements", "报销", Reimbursement, scope_finance, "/reimbursements?item={id}", "description", ("description",),
     "owner__name"),
    # only for whoever can open the 经费来源 page (managers); others pick a fund in their forms
    ("funds", "经费来源", Fund, lambda funds, user: scope_group(funds, user) if is_manager(user) else funds.none(), "/funds", "name", ("name", "code"), "code"),
    # applicants are not members yet (the member list leaves them out too)
    ("members", "成员", User, lambda users, user: scope_group(users.filter(pending=False), user), "/members", "name", ("name", "research_direction"), "research_direction"),
    ("equipment", "设备", Equipment, scope_group, "/equipment/{id}", "name",
     ("name", "code", "model", "category", "location"), "code"),
    ("specimens", "试件", Specimen, scope_group, "/specimens/{id}", "name",
     ("name", "code", "material", "location"), "code"),
    ("consumables", "耗材", Consumable, scope_group, "/consumables?item={id}", "name",
     ("name", "spec", "location"), "spec"),
    ("knowledge", "知识库", Doc, scope_group, "/knowledge?doc={id}", "title", ("title",), None),
    ("meetings", "组会", Meeting, scope_group, "/meetings/{id}", "title", ("title", "minutes", "agenda__topic"), "date"),
    ("actions", "行动项", ActionItem, scoped(scope_group, "meeting__group"), "/meetings/{meeting_id}", "content", ("content",),
     "owner__name"),
    ("achievements", "成果", Achievement, scope_group, "/achievements?item={id}", "title", ("title",), None),
)


CODES = {Experiment: "EX", ProcessingRun: "RUN", Dataset: "DS", PurchaseRequest: "PR", Reimbursement: "RB"}
LINK_FIELDS = re.compile(r"{(\w+)}")


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
            if model is User and is_supervisor(request.user):  # students never see login names, nor probe them
                fields = (*fields, "username")
            matches = code_lookup(q, CODES[model]) if model in CODES else None
            if matches is None:
                matches = reduce(or_, (Q(**{f"{field}__icontains": q}) for field in fields))
            links = [name for name in LINK_FIELDS.findall(link) if name != "id"]
            selected = dict.fromkeys(["pk", title, *([subtitle] if subtitle else []), *links])
            rows = queryset.filter(matches).order_by("-pk").values(*selected).distinct()[:LIMIT]
            items = []
            for row in rows:
                pk = row["pk"]
                target = link.format(id=pk, **{name: row[name] for name in links})
                items.append({
                    "id": pk,
                    "title": str(row[title])[:160] if row[title] else f"{label} #{pk}",
                    "subtitle": str(row[subtitle]) if subtitle and row[subtitle] is not None else "",
                    "link": target,
                })
            if items:
                results.append({"module": key, "label": label, "items": items})
        return Response(results, headers={"Cache-Control": "private, no-store"})
