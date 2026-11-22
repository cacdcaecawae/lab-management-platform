from datetime import timedelta

from django.db import transaction
from django.db.models import Exists, F, Max, OuterRef, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.filters import SearchFilter
from rest_framework.response import Response

from core.exceptions import Conflict
from core.permissions import IsActiveMember, IsManager, is_manager, scope_group

from .models import Batch, Consumable, StockTxn
from .queries import batch_details, batches_with_balance
from .serializers import BatchModeSerializer, ConsumableSerializer, StockTxnSerializer

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
    filter_backends = [SearchFilter]
    search_fields = ["name", "spec", "location"]

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
        if self.action == "list" and (item := self.request.query_params.get("item")):
            return consumables.filter(pk=item) if item.isascii() and item.isdigit() and len(item) <= 18 else consumables.none()
        if self.action == "list" and self.request.query_params.get("low") == "1":
            consumables = consumables.filter(stock__lt=F("safety_stock"))
        if self.action == "list" and (days := self.request.query_params.get("expiring_within")) is not None:
            if not days.isascii() or not days.isdigit() or len(days) > 3 or not 0 <= int(days) <= 365:
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
        return Response(serializer.data, status=status.HTTP_201_CREATED)
