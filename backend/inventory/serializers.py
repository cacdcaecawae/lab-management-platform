from django.db import IntegrityError, transaction
from rest_framework import serializers

from accounts.serializers import UserBriefSerializer
from core.exceptions import Conflict
from core.permissions import scope_group
from core.serializers import ProjectBriefSerializer
from procurement.serializers import ArrivedPurchaseField, PurchaseRefSerializer
from projects.serializers import GroupProjectField

from .models import Consumable, StockTxn


class ConsumableSerializer(serializers.ModelSerializer):
    stock = serializers.SerializerMethodField()
    stock_version = serializers.IntegerField(read_only=True, default=0)
    low = serializers.SerializerMethodField()

    class Meta:
        model = Consumable
        fields = ["id", "name", "spec", "unit", "location", "safety_stock", "stock", "stock_version", "low", "notes", "created_at", "updated_at"]

    def get_stock(self, consumable):
        # ConsumableViewSet annotates stock; a just-created item has no transactions yet.
        return getattr(consumable, "stock", 0)

    def get_low(self, consumable):
        return self.get_stock(consumable) < consumable.safety_stock

    def validate(self, attrs):
        name = attrs.get("name", getattr(self.instance, "name", ""))
        spec = attrs.get("spec", getattr(self.instance, "spec", ""))
        same = scope_group(Consumable.objects.filter(name=name, spec=spec), self.context["request"].user)
        if self.instance:
            same = same.exclude(pk=self.instance.pk)
        if same.exists():
            raise Conflict("本组已有同名同规格的耗材")
        return attrs

    def save(self, **kwargs):
        try:
            with transaction.atomic():
                return super().save(**kwargs)
        except IntegrityError:  # a concurrent request created the same name + spec after validate()
            raise Conflict("本组已有同名同规格的耗材")


class StockTxnSerializer(serializers.ModelSerializer):
    """Clients send a positive quantity for in / out / return and the signed difference for adjust;
    the stored (and returned) quantity is signed: out is negative."""

    stock_version_seen = serializers.IntegerField(write_only=True, required=False, min_value=0)
    handler = UserBriefSerializer(read_only=True)
    project = ProjectBriefSerializer(read_only=True)
    project_id = GroupProjectField(source="project", write_only=True, required=False, allow_null=True)
    purchase = PurchaseRefSerializer(read_only=True)  # group-visible: the code only, not who bought what for what
    purchase_id = ArrivedPurchaseField(source="purchase", write_only=True, required=False, allow_null=True)

    class Meta:
        model = StockTxn
        fields = ["id", "kind", "quantity", "stock_version_seen", "handler", "project", "project_id", "purchase", "purchase_id", "note", "created_at"]

    def validate(self, attrs):
        if attrs.get("purchase") and attrs["kind"] != StockTxn.Kind.IN:
            raise serializers.ValidationError({"purchase_id": ["只有入库可以关联采购申请"]})
        quantity = attrs["quantity"]
        if attrs["kind"] == StockTxn.Kind.ADJUST:
            if "stock_version_seen" not in attrs:
                raise serializers.ValidationError({"stock_version_seen": ["盘点必须提交打开页面时的库存流水版本"]})
            if quantity == 0:
                raise serializers.ValidationError({"quantity": ["调整数量不能为 0"]})
        elif quantity <= 0:
            raise serializers.ValidationError({"quantity": ["数量必须是正整数"]})
        elif attrs["kind"] == StockTxn.Kind.OUT:
            attrs["quantity"] = -quantity
        return attrs
