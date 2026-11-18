from decimal import Decimal
from pathlib import Path

from django.db import IntegrityError, transaction
from rest_framework import serializers

from accounts.models import ResearchGroup
from accounts.serializers import UserBriefSerializer
from core.exceptions import Conflict
from core.permissions import scope_group, scope_private
from projects.serializers import GroupMemberField

from .models import Approval, Attachment, Fund, PurchaseItem, PurchaseRequest, Reimbursement

ATTACHMENT_TYPES = {".pdf", ".jpg", ".jpeg", ".png"}
ATTACHMENT_MAX_SIZE = 20 * 1024**2
MONEY = {"max_digits": 12, "decimal_places": 2}
MAX_TOTAL = Decimal("9999999999.99")  # the most MONEY can show; the total is computed on read


class FundSerializer(serializers.ModelSerializer):
    owner = UserBriefSerializer(read_only=True)
    owner_id = GroupMemberField(source="owner", write_only=True, required=False, allow_null=True)

    class Meta:
        model = Fund
        fields = ["id", "name", "code", "owner", "owner_id", "active", "notes", "created_at", "updated_at"]

    def validate_code(self, value):
        same = scope_group(Fund.objects.filter(code=value), self.context["request"].user)
        if self.instance:
            same = same.exclude(pk=self.instance.pk)
        if same.exists():
            raise Conflict("本组已有相同经费号")
        return value

    def save(self, **kwargs):
        try:
            with transaction.atomic():
                return super().save(**kwargs)
        except IntegrityError:  # a concurrent request took the same code after validate_code
            raise Conflict("本组已有相同经费号") from None


class FundBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fund
        fields = ["id", "code", "name", "active"]


class ActiveFundField(serializers.PrimaryKeyRelatedField):
    """An active fund of the requesting user's group. A stopped fund stays on old records but cannot be picked."""

    def get_queryset(self):
        return scope_group(Fund.objects.filter(active=True), self.context["request"].user)


class AttachmentSerializer(serializers.ModelSerializer):
    uploaded_by = UserBriefSerializer(read_only=True)
    url = serializers.SerializerMethodField()

    class Meta:
        model = Attachment
        fields = ["id", "kind", "name", "size", "uploaded_by", "url", "created_at", "file"]
        read_only_fields = ["name", "size"]
        extra_kwargs = {"file": {"write_only": True}}

    def get_url(self, attachment):
        return f"/api/attachments/{attachment.id}/file/"

    def validate_file(self, file):
        if Path(file.name).suffix.lower() not in ATTACHMENT_TYPES:
            raise serializers.ValidationError("附件只支持 PDF、JPG、PNG")
        if file.size > ATTACHMENT_MAX_SIZE:
            raise serializers.ValidationError("附件不能超过 20 MB")
        return file

    def create(self, validated_data):
        file = validated_data["file"]  # Django's multipart parser already strips any directory from the name
        return super().create({**validated_data, "name": (file.name or "附件")[-200:], "size": file.size})


class PurchaseItemSerializer(serializers.ModelSerializer):
    unit_price = serializers.DecimalField(**MONEY, min_value=Decimal("0"))
    quantity = serializers.IntegerField(min_value=1, max_value=1_000_000)
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseItem
        fields = ["id", "name", "spec", "quantity", "unit_price", "subtotal", "link"]
        read_only_fields = ["id"]

    def get_subtotal(self, item):
        return f"{item.quantity * item.unit_price:.2f}"


class ApprovalSerializer(serializers.ModelSerializer):
    reviewer = UserBriefSerializer(read_only=True)

    class Meta:
        model = Approval
        fields = ["id", "stage", "reviewer", "verdict", "comment", "total", "created_at"]


class PurchaseBriefSerializer(serializers.ModelSerializer):
    owner = UserBriefSerializer(read_only=True)

    class Meta:
        model = PurchaseRequest
        fields = ["id", "code", "owner", "purpose", "status"]


class PurchaseRefSerializer(serializers.ModelSerializer):
    """For group-visible records (equipment, stock-in): the applicant and purpose are private."""

    class Meta:
        model = PurchaseRequest
        fields = ["id", "code"]


class PurchaseSerializer(serializers.ModelSerializer):
    owner = UserBriefSerializer(read_only=True)
    fund = FundBriefSerializer(read_only=True)
    fund_id = ActiveFundField(source="fund", write_only=True, required=False, allow_null=True)
    items = PurchaseItemSerializer(many=True, required=False)
    total = serializers.DecimalField(**MONEY, read_only=True)
    # Set by PurchaseViewSet: a draft whose last submission was sent back with a comment.
    returned = serializers.BooleanField(read_only=True, default=False)

    class Meta:
        model = PurchaseRequest
        fields = [
            "id", "code", "owner", "fund", "fund_id", "purpose", "status", "items", "total", "returned",
            "submitted_at", "created_at", "updated_at",
        ]
        read_only_fields = ["status", "submitted_at"]

    def validate_items(self, items):
        if sum(i["quantity"] * i["unit_price"] for i in items) > MAX_TOTAL:
            raise serializers.ValidationError("合计不能超过 9,999,999,999.99 元，请检查数量和单价")
        return items

    def create(self, validated_data):
        items = validated_data.pop("items", [])
        purchase = super().create(validated_data)
        PurchaseItem.objects.bulk_create(PurchaseItem(request=purchase, **item) for item in items)
        return purchase

    def update(self, purchase, validated_data):
        # The view holds the row lock and decides what the edit does to the approval state (see PurchaseViewSet.update).
        items = validated_data.pop("items", None)
        purchase = super().update(purchase, validated_data)
        if items is not None:  # the list replaces all items
            purchase.items.all().delete()
            PurchaseItem.objects.bulk_create(PurchaseItem(request=purchase, **item) for item in items)
        return purchase


class PurchaseDetailSerializer(PurchaseSerializer):
    approvals = ApprovalSerializer(many=True, read_only=True)
    attachments = AttachmentSerializer(many=True, read_only=True)
    linked_equipment = serializers.SerializerMethodField()
    linked_stock = serializers.SerializerMethodField()

    class Meta(PurchaseSerializer.Meta):
        fields = PurchaseSerializer.Meta.fields + ["approvals", "attachments", "linked_equipment", "linked_stock"]

    def get_linked_equipment(self, purchase):
        return [{"id": e.id, "code": e.code, "name": e.name} for e in purchase.equipment.order_by("code")]

    def get_linked_stock(self, purchase):
        txns = purchase.stock_txns.select_related("consumable").order_by("created_at")
        return [{"id": t.id, "consumable": str(t.consumable), "quantity": t.quantity, "created_at": t.created_at} for t in txns]


class ReviewSerializer(serializers.Serializer):
    verdict = serializers.ChoiceField(choices=Approval.Verdict.choices)
    comment = serializers.CharField(required=False, allow_blank=True, default="")
    # What the reviewer was looking at: a decision belongs to that submission, state and total.
    status_seen = serializers.ChoiceField(choices=PurchaseRequest.Status.choices)
    total_seen = serializers.DecimalField(**MONEY)
    submitted_seen = serializers.DateTimeField()

    def validate(self, attrs):
        attrs["comment"] = attrs["comment"].strip()
        if attrs["verdict"] == Approval.Verdict.RETURN and not attrs["comment"]:
            raise serializers.ValidationError({"comment": ["退回时必须写明意见"]})
        return attrs


class VisiblePurchaseField(serializers.PrimaryKeyRelatedField):
    """A purchase request the requesting user can see; ReimbursementSerializer.validate narrows it to the owner's."""

    def get_queryset(self):
        return scope_private(PurchaseRequest.objects.all(), self.context["request"].user)


class ReimbursementSerializer(serializers.ModelSerializer):
    owner = UserBriefSerializer(read_only=True)
    fund = FundBriefSerializer(read_only=True)
    fund_id = ActiveFundField(source="fund", write_only=True)
    purchase = PurchaseBriefSerializer(read_only=True)
    purchase_id = VisiblePurchaseField(source="purchase", write_only=True, required=False, allow_null=True)
    amount = serializers.DecimalField(**MONEY, min_value=Decimal("0.01"))
    attachments = AttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = Reimbursement
        fields = [
            "id", "code", "owner", "fund", "fund_id", "purchase", "purchase_id", "category", "amount", "occurred_on",
            "description", "status", "submitted_at", "paid_at", "attachments", "created_at", "updated_at",
        ]
        read_only_fields = ["status", "submitted_at", "paid_at"]

    def validate(self, attrs):
        # Also when a manager edits someone's record: the linked purchase must be the reimbursing person's own.
        purchase = attrs.get("purchase")
        owner_id = self.instance.owner_id if self.instance else self.context["request"].user.id
        if purchase and purchase.owner_id != owner_id:
            raise serializers.ValidationError({"purchase_id": ["只能关联报销人自己的采购申请"]})
        return attrs


class AdvanceSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Reimbursement.Status.choices)


class ArrivedPurchaseField(serializers.PrimaryKeyRelatedField):
    """An arrived purchase request of the requesting manager's group (equipment and stock-in forms link one)."""

    def get_queryset(self):
        return scope_private(
            PurchaseRequest.objects.filter(status=PurchaseRequest.Status.ARRIVED), self.context["request"].user
        )


class FinanceEmailSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResearchGroup
        fields = ["finance_email"]
