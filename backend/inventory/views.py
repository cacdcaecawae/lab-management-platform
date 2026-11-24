from datetime import timedelta

from django.db import transaction
from django.db.models import Exists, F, Max, OuterRef, Subquery, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import content_disposition_header
from openpyxl import Workbook
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from core.exceptions import Conflict
from core.export import xlsx_bytes
from core.filters import Ordering, Search, equal
from core.notifications import notify
from core.params import plain_int
from core.permissions import IsActiveMember, IsManager, is_manager, is_supervisor, scope_group

from .models import Batch, Consumable, StockTxn
from .queries import batch_details, batches_with_balance
from .serializers import BatchModeSerializer, ConsumableSerializer, LedgerTxnSerializer, StockTxnSerializer

MANAGER_ONLY = {StockTxn.Kind.IN, StockTxn.Kind.ADJUST}


def add_to_batch(item, batch_no, expiry_given=False, expiry=None):
    batch, created = Batch.objects.get_or_create(consumable=item, batch_no=batch_no, defaults={"expires_on": expiry})
    if not created and expiry_given and expiry != batch.expires_on:
        raise ValidationError({"expires_on": ["该批号已有不同有效期，请核对批号"]})
    return batch


def lock_item(item, user):
    # All stock and mode mutations are serialized on the same group-scoped row.
    return get_object_or_404(scope_group(Consumable.objects.select_for_update(), user), pk=item.pk)


def ledger_state(item):
    return item.txns.aggregate(total=Sum("quantity", default=0), version=Max("id", default=0))


def check_version(actual, seen):
    if actual != seen:
        raise Conflict("库存流水已变化，请刷新后重新核对", code="stale_stock")



class ConsumableViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Group-wide read; managers create and edit items, stock in and adjust. Members record their own
    take-outs and returns. No delete, and transactions are never edited: mistakes get an adjust entry."""

    http_method_names = ["get", "post", "patch", "head", "options"]
    serializer_class = ConsumableSerializer
    filter_backends = [Search, Ordering]
    search_fields = ["name", "spec", "category", "location"]
    ordering_fields = ["name", "stock", "nearest_expiry_on"]

    def get_permissions(self):
        if self.action in ("create", "partial_update", "batch_mode"):
            return [IsActiveMember(), IsManager()]
        return [IsActiveMember()]

    def get_queryset(self):
        # Explicit order_by: Django drops Meta.ordering on aggregated (GROUP BY) querysets.
        consumables = (
            scope_group(Consumable.objects.all(), self.request.user)
            .annotate(stock=Sum("txns__quantity", default=0), stock_version=Max("txns__id", default=0))
            .order_by("name", "spec", "id")
            .prefetch_related(batch_details())
        )
        if self.action == "list":  # for sorting by 最近到期: the earliest expiry among batches still in stock
            nearest = batches_with_balance().filter(consumable=OuterRef("pk"), stock__gt=0, expires_on__isnull=False)
            consumables = consumables.annotate(nearest_expiry_on=Subquery(nearest.values("expires_on")[:1]))
            consumables = equal(consumables, self.request.query_params, category="category", location="location")
        if self.action == "list" and (item := self.request.query_params.get("item")):
            return consumables.filter(pk=item) if plain_int(item) else consumables.none()
        if self.action == "list" and self.request.query_params.get("low") == "1":
            consumables = consumables.filter(stock__lt=F("safety_stock"))
        if self.action == "list" and (days := self.request.query_params.get("expiring_within")) is not None:
            if plain_int(days, 3) is None or int(days) > 365:
                raise ValidationError({"expiring_within": ["须为 0 至 365 天"]})
            today = timezone.localdate()
            expiring = batches_with_balance().filter(
                consumable_id=OuterRef("pk"), expires_on__lte=today + timedelta(days=int(days)), stock__gt=0,
            )
            consumables = consumables.filter(tracks_batches=True).filter(Exists(expiring))
        return consumables

    def filter_queryset(self, queryset):
        if self.action == "list" and self.request.query_params.get("item"):
            return queryset  # exact search destination is independent of the list keyword
        return super().filter_queryset(queryset)

    def perform_create(self, serializer):
        serializer.save(group=self.request.user.group)

    @action(detail=True, methods=["post"], url_path="batch-mode")
    def batch_mode(self, request, pk=None):
        item = self.get_object()
        payload = BatchModeSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        requested = payload.validated_data["tracks_batches"]
        opening = payload.validated_data.get("opening_batch")
        with transaction.atomic():
            locked = lock_item(item, request.user)
            ledger = ledger_state(locked)
            check_version(ledger["version"], payload.validated_data["stock_version_seen"])
            if opening and (not requested or locked.tracks_batches or not ledger["total"]):
                raise ValidationError({"opening_batch": ["仅在开启批次管理且现有库存大于 0 时填写期初批次"]})
            if requested != locked.tracks_batches:
                if requested and ledger["total"] and not opening:
                    raise Conflict("当前库存大于 0，需明确填写期初批次", code="opening_batch_required")
                if not requested and batches_with_balance().filter(consumable=locked).exclude(stock=0).exists():
                    raise Conflict("所有批次结余为 0 后才可关闭", code="batches_not_empty")
                if opening:
                    batch = add_to_batch(locked, opening["batch_no"], "expires_on" in opening, opening.get("expires_on"))
                    remaining = ledger["total"]
                    if remaining < 0:
                        raise Conflict("负库存不能分配，请先核对账本", code="negative_stock")
                    # Split at the IntegerField limit; large aggregate balances can exceed one row.
                    changes = []
                    while remaining:
                        amount = min(remaining, 2_147_483_647)
                        changes.extend([
                            StockTxn(consumable=locked, kind=StockTxn.Kind.ALLOCATION, quantity=-amount, handler=request.user),
                            StockTxn(consumable=locked, batch=batch, kind=StockTxn.Kind.ALLOCATION, quantity=amount, handler=request.user),
                        ])
                        remaining -= amount
                    StockTxn.objects.bulk_create(changes)
                locked.tracks_batches = requested
                locked.save(update_fields=["tracks_batches", "updated_at"])
                StockTxn.objects.create(consumable=locked, kind=StockTxn.Kind.BATCH_MODE, quantity=0, handler=request.user,
                                        note="开启批次管理" if requested else "关闭批次管理")
            result = self.get_serializer(self.get_queryset().get(pk=locked.pk)).data
        return Response(result)

    @action(detail=True, methods=["get", "post"], serializer_class=StockTxnSerializer)
    def txns(self, request, pk=None):
        consumable = self.get_object()
        if request.method == "GET":
            page = self.paginate_queryset(consumable.txns.select_related("handler", "project", "purchase", "batch"))
            return self.get_paginated_response(self.get_serializer(page, many=True).data)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data["kind"] in MANAGER_ONLY and not is_manager(request.user):
            raise PermissionDenied("入库和盘点调整只限管理员")
        seen = serializer.validated_data.pop("stock_version_seen", None)
        with transaction.atomic():
            locked = lock_item(consumable, request.user)
            ledger = ledger_state(locked)
            data = serializer.validated_data
            kind = data["kind"]
            if kind == StockTxn.Kind.ADJUST:
                check_version(ledger["version"], seen)
            batch_id = data.pop("batch_id", None)
            batch_no = data.pop("batch_no", None)
            expiry_given = "expires_on" in data
            expires_on = data.pop("expires_on", None)
            batch = None
            if locked.tracks_batches:
                if kind == StockTxn.Kind.IN:
                    if batch_id or not batch_no:
                        raise ValidationError({"batch_no": ["按批次入库时必须填写批号"]})
                    batch = add_to_batch(locked, batch_no, expiry_given, expires_on)
                else:
                    if not batch_id or batch_no or expiry_given:
                        raise ValidationError({"batch_id": ["请选择该耗材的批次"]})
                    batch = locked.batches.filter(pk=batch_id).first()
                    if batch is None:
                        raise ValidationError({"batch_id": ["请选择该耗材的批次"]})
                    if kind == StockTxn.Kind.OUT and batch.expires_on and batch.expires_on < timezone.localdate():
                        raise ValidationError({"batch_id": ["该批次已过期，不能领用"]})
                batch_stock = batch.txns.aggregate(total=Sum("quantity", default=0))["total"]
                if batch_stock + data["quantity"] < 0:
                    raise ValidationError({"quantity": [f"该批次库存不足：当前 {batch_stock} {locked.unit}"]})
            elif batch_id or batch_no or expiry_given:
                raise ValidationError({"batch_id": ["耗材未启用批次管理"]})
            stock = ledger["total"]
            if stock + data["quantity"] < 0:
                raise ValidationError({"quantity": [f"库存不足：当前 {stock} {locked.unit}"]})
            serializer.save(consumable=locked, handler=request.user, batch=batch)
            # Only the step across the line: it is said once, and again only after a restock lifted it above.
            if stock >= locked.safety_stock > stock + data["quantity"]:
                notify(locked.group_id, "耗材低于安全库存", "/consumables", role="manager",
                       body=f"{locked} 剩 {stock + data['quantity']} {locked.unit}，安全库存 {locked.safety_stock}")
        return Response(serializer.data, status=status.HTTP_201_CREATED)


def local_day(text, name):
    try:
        day = parse_date(text)
    except ValueError:  # 2026-13-45: the right shape, not a date
        day = None
    if day is None:
        raise ValidationError({name: ["格式为 YYYY-MM-DD"]})
    return day


class StockTxnViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """The group's ledger across consumables, newest first: advisors and managers see every entry, others only what
    they handled themselves. Filters: consumable, kind, handler, project, from / to (YYYY-MM-DD, local). The export
    holds exactly what the list shows."""

    serializer_class = LedgerTxnSerializer

    def get_queryset(self):
        user = self.request.user
        txns = scope_group(
            StockTxn.objects.select_related("consumable", "batch", "handler", "project", "purchase"), user, "consumable__group"
        )
        if not is_supervisor(user):
            txns = txns.filter(handler=user)
        params = self.request.query_params
        if kind := params.get("kind"):
            txns = txns.filter(kind=kind) if kind in StockTxn.Kind.values else txns.none()
        txns = equal(txns, params, consumable="consumable_id", handler="handler_id", project="project_id")
        if params.get("from"):
            txns = txns.filter(created_at__date__gte=local_day(params["from"], "from"))
        if params.get("to"):
            txns = txns.filter(created_at__date__lte=local_day(params["to"], "to"))
        return txns.order_by("-created_at", "-id")

    @action(detail=False)
    def export(self, request):
        book = Workbook()
        sheet = book.active
        sheet.title = "耗材流水"
        sheet.append(["时间", "耗材", "规格", "类型", "批号", "数量", "单位", "经手人", "项目", "采购申请", "备注"])
        for txn in self.get_queryset():
            sheet.append([
                timezone.localtime(txn.created_at).strftime("%Y-%m-%d %H:%M"), txn.consumable.name, txn.consumable.spec,
                txn.get_kind_display(), txn.batch.batch_no if txn.batch else "", txn.quantity, txn.consumable.unit,
                txn.handler.display_name, txn.project.name if txn.project else "", txn.purchase.code if txn.purchase else "",
                txn.note,
            ])
        response = HttpResponse(xlsx_bytes(book), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        filename = f"耗材流水-{timezone.localdate():%Y%m%d}.xlsx"
        response["Content-Disposition"] = content_disposition_header(as_attachment=True, filename=filename)
        return response
