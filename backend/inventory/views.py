from django.db import transaction
from django.db.models import F, Sum
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.filters import SearchFilter
from rest_framework.response import Response

from core.permissions import IsActiveMember, IsManager, is_manager, scope_group

from .models import Consumable, StockTxn
from .serializers import ConsumableSerializer, StockTxnSerializer

MANAGER_ONLY = {StockTxn.Kind.IN, StockTxn.Kind.ADJUST}


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
        if self.action in ("create", "partial_update"):
            return [IsActiveMember(), IsManager()]
        return [IsActiveMember()]

    def get_queryset(self):
        # Explicit order_by: Django drops Meta.ordering on aggregated (GROUP BY) querysets.
        consumables = (
            scope_group(Consumable.objects.all(), self.request.user)
            .annotate(stock=Sum("txns__quantity", default=0))
            .order_by("name", "spec", "id")
        )
        if self.action == "list" and self.request.query_params.get("low") == "1":
            consumables = consumables.filter(stock__lt=F("safety_stock"))
        return consumables

    def perform_create(self, serializer):
        serializer.save(group=self.request.user.group)

    @action(detail=True, methods=["get", "post"], serializer_class=StockTxnSerializer)
    def txns(self, request, pk=None):
        consumable = self.get_object()
        if request.method == "GET":
            page = self.paginate_queryset(consumable.txns.select_related("handler", "project", "purchase"))
            return self.get_paginated_response(self.get_serializer(page, many=True).data)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data["kind"] in MANAGER_ONLY and not is_manager(request.user):
            raise PermissionDenied("入库和盘点调整只限管理员")
        with transaction.atomic():
            # Locked so two concurrent take-outs cannot both pass the stock check.
            locked = Consumable.objects.select_for_update().get(pk=consumable.pk)
            stock = locked.txns.aggregate(total=Sum("quantity", default=0))["total"]
            if stock + serializer.validated_data["quantity"] < 0:
                raise ValidationError({"quantity": [f"库存不足：当前 {stock} {locked.unit}"]})
            serializer.save(consumable=locked, handler=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
