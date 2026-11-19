from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers

from accounts.serializers import UserBriefSerializer
from core.exceptions import Conflict
from core.permissions import scope_group
from procurement.serializers import ArrivedPurchaseField, PurchaseRefSerializer
from projects.serializers import GroupProjectField, ProjectBriefSerializer

from .models import Batch, Consumable, StockTxn


class BatchSerializer(serializers.ModelSerializer):
    stock = serializers.IntegerField(read_only=True)
    can_issue = serializers.SerializerMethodField()

    def get_can_issue(self, batch):
        return batch.stock > 0 and (batch.expires_on is None or batch.expires_on >= timezone.localdate())

    class Meta:
        model = Batch
        fields = ["id", "batch_no", "expires_on", "stock", "can_issue"]


class OpeningBatchSerializer(serializers.Serializer):
    batch_no = serializers.CharField(max_length=50)
    expires_on = serializers.DateField(allow_null=True, required=False)


class BatchModeSerializer(serializers.Serializer):
    tracks_batches = serializers.BooleanField()
    stock_version_seen = serializers.IntegerField(min_value=0)
    opening_batch = OpeningBatchSerializer(required=False)


class ConsumableSerializer(serializers.ModelSerializer):
    stock = serializers.SerializerMethodField()
    stock_version = serializers.IntegerField(read_only=True, default=0)
    low = serializers.SerializerMethodField()
    batches = BatchSerializer(source="stock_batches", many=True, read_only=True, default=list)
    nearest_expiry = serializers.SerializerMethodField()

    def get_nearest_expiry(self, consumable):
        if not consumable.tracks_batches:
            return None
        return next((b.expires_on.isoformat() for b in getattr(consumable, "stock_batches", ()) if b.stock > 0 and b.expires_on), None)

    class Meta:
        model = Consumable
        fields = ["id", "name", "spec", "unit", "location", "safety_stock", "stock", "stock_version", "low", "tracks_batches", "batches", "nearest_expiry", "notes", "created_at", "updated_at"]

        read_only_fields = ["tracks_batches"]

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

    def update(self, instance, validated_data):
        # Metadata writes must not overwrite concurrently changed batch mode.
        for name, value in validated_data.items():
            setattr(instance, name, value)
        if validated_data:
            instance.save(update_fields=[*validated_data, "updated_at"])
        return instance

    def save(self, **kwargs):
        try:
            with transaction.atomic():
                return super().save(**kwargs)
        except IntegrityError:  # a concurrent request created the same name + spec after validate()
            raise Conflict("本组已有同名同规格的耗材")


class StockTxnSerializer(serializers.ModelSerializer):
    """Clients send a positive quantity for in / out / return and the signed difference for adjust;
    the stored (and returned) quantity is signed: out is negative."""

    batch = OpeningBatchSerializer(read_only=True)
    batch_id = serializers.IntegerField(min_value=1, max_value=2**63 - 1, required=False, write_only=True)
    batch_no = serializers.CharField(max_length=50, required=False, write_only=True)
    expires_on = serializers.DateField(required=False, allow_null=True, write_only=True)
    stock_version_seen = serializers.IntegerField(write_only=True, required=False, min_value=0)
    handler = UserBriefSerializer(read_only=True)
    project = ProjectBriefSerializer(read_only=True)
    project_id = GroupProjectField(source="project", write_only=True, required=False, allow_null=True)
    purchase = PurchaseRefSerializer(read_only=True)  # group-visible: the code only, not who bought what for what
    purchase_id = ArrivedPurchaseField(source="purchase", write_only=True, required=False, allow_null=True)

    class Meta:
        model = StockTxn
        fields = ["id", "kind", "quantity", "stock_version_seen", "batch", "batch_id", "batch_no", "expires_on", "handler", "project", "project_id", "purchase", "purchase_id", "note", "created_at"]

    def validate(self, attrs):
        if attrs["kind"] in (StockTxn.Kind.ALLOCATION, StockTxn.Kind.BATCH_MODE):
            raise serializers.ValidationError({"kind": ["内部流水类型不能由客户端创建"]})
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
