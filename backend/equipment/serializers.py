from datetime import timedelta
from pathlib import Path

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers

from accounts.serializers import UserBriefSerializer
from core.exceptions import Conflict
from core.permissions import scope_group
from procurement.serializers import ArrivedPurchaseField, PurchaseRefSerializer
from projects.serializers import GroupMemberField, GroupProjectField, ProjectBriefSerializer

from .models import Booking, Equipment, UsageReport


class EquipmentBriefSerializer(serializers.ModelSerializer):
    """Embedded in bookings, experiments, knowledge docs and the workbench."""

    class Meta:
        model = Equipment
        fields = ["id", "code", "name", "status"]


# A booking may start this much before "now": the time spent filling in the form, and clock differences.
START_GRACE = timedelta(minutes=5)
# A typo'd year must not block a device for months; longer experiments book back-to-back parts.
MAX_USE = timedelta(days=7)
PHOTO_TYPES = {".jpg", ".jpeg", ".png", ".webp"}
PHOTO_MAX_SIZE = 10 * 1024**2


class GroupEquipmentField(serializers.PrimaryKeyRelatedField):
    """An equipment id from the requesting user's research group."""

    def get_queryset(self):
        return scope_group(Equipment.objects.all(), self.context["request"].user)


class EquipmentSerializer(serializers.ModelSerializer):
    custodian = UserBriefSerializer(read_only=True)
    custodian_id = GroupMemberField(source="custodian", write_only=True, required=False, allow_null=True)
    in_use = serializers.SerializerMethodField()
    purchase = PurchaseRefSerializer(read_only=True)  # group-visible: the code only, not who bought what for what
    purchase_id = ArrivedPurchaseField(source="purchase", write_only=True, required=False, allow_null=True)
    # The status the edit form showed when it opened; required with a status change (see update()).
    status_seen = serializers.ChoiceField(choices=Equipment.Status.choices, write_only=True, required=False)

    class Meta:
        model = Equipment
        fields = [
            "id", "code", "name", "model", "category", "location", "custodian", "custodian_id", "status", "status_seen",
            "in_use", "purchase_date", "calibration_due", "notes", "purchase", "purchase_id", "created_at", "updated_at",
        ]

    def get_in_use(self, equipment):
        # EquipmentViewSet annotates in_use; a just-created item has no bookings yet.
        return getattr(equipment, "in_use", False)

    def validate_code(self, value):
        same_code = scope_group(Equipment.objects.filter(code=value), self.context["request"].user)
        if self.instance:
            same_code = same_code.exclude(pk=self.instance.pk)
        if same_code.exists():
            raise Conflict("本组已有相同编号的设备")
        return value

    def validate(self, attrs):
        if not self.instance:
            attrs.pop("status_seen", None)  # nothing was seen before the device existed
        elif "status" in attrs and "status_seen" not in attrs:
            raise serializers.ValidationError({"status_seen": ["修改状态时必须提交打开编辑框时看到的状态"]})
        return attrs

    def save(self, **kwargs):
        try:
            with transaction.atomic():
                return super().save(**kwargs)
        except IntegrityError:  # a concurrent request took the same code after validate_code
            raise Conflict("本组已有相同编号的设备")

    def update(self, instance, validated_data):
        # Re-read under the row lock (inside save()'s transaction): fields the request did not send keep their
        # latest value, e.g. a "needs_check" an abnormal report committed after get_object() read the row (F1).
        # No select_related here: FOR UPDATE cannot follow the nullable custodian join.
        locked = Equipment.objects.select_for_update().get(pk=instance.pk)
        locked.in_use = getattr(instance, "in_use", False)
        # A status chosen in a form that showed another status is a decision made on an old picture, e.g. "repair"
        # picked before an abnormal report set "needs_check" (R1). Writing the value it already has is harmless.
        seen = validated_data.pop("status_seen", None)
        new = validated_data.get("status")
        if new is not None and locked.status not in (seen, new):
            current, opened = locked.get_status_display(), Equipment.Status(seen).label
            raise Conflict(f"设备状态已被改为“{current}”（你打开时是“{opened}”），请重新打开编辑框确认", code="stale_status")
        return super().update(locked, validated_data)


class UsageReportSerializer(serializers.ModelSerializer):
    photo_url = serializers.SerializerMethodField()

    class Meta:
        model = UsageReport
        fields = ["condition", "description", "photo", "photo_url", "reported_at"]
        extra_kwargs = {"photo": {"write_only": True, "required": False}}

    def get_photo_url(self, report):
        return f"/api/bookings/{report.booking_id}/photo/" if report.photo else None

    def validate_photo(self, photo):
        if Path(photo.name).suffix.lower() not in PHOTO_TYPES:
            raise serializers.ValidationError("照片只支持 JPG、PNG、WebP")
        if photo.size > PHOTO_MAX_SIZE:
            raise serializers.ValidationError("照片不能超过 10 MB")
        return photo

    def validate(self, attrs):
        attrs["description"] = attrs.get("description", "").strip()
        if attrs["condition"] == UsageReport.Condition.ABNORMAL and not attrs["description"]:
            raise serializers.ValidationError({"description": ["登记异常时必须写明情况"]})
        return attrs


class BookingSerializer(serializers.ModelSerializer):
    equipment = EquipmentBriefSerializer(read_only=True)
    equipment_id = GroupEquipmentField(source="equipment", write_only=True)
    user = UserBriefSerializer(read_only=True)
    project = ProjectBriefSerializer(read_only=True)
    project_id = GroupProjectField(source="project", write_only=True, required=False, allow_null=True)
    report = UsageReportSerializer(read_only=True)

    class Meta:
        model = Booking
        fields = [
            "id", "equipment", "equipment_id", "user", "project", "project_id", "kind", "start_at", "end_at",
            "purpose", "cancelled_at", "planned_end_at", "report", "created_at",
        ]
        read_only_fields = ["cancelled_at", "planned_end_at"]

    def validate(self, attrs):
        if attrs["end_at"] <= attrs["start_at"]:
            raise serializers.ValidationError({"end_at": ["结束时间必须晚于开始时间"]})
        if attrs["start_at"] < timezone.now() - START_GRACE:
            raise serializers.ValidationError({"start_at": ["开始时间不能早于当前时间"]})
        if attrs.get("kind", Booking.Kind.USE) == Booking.Kind.USE and attrs["end_at"] - attrs["start_at"] > MAX_USE:
            raise serializers.ValidationError({"end_at": ["一次预约不能超过 7 天，更长的实验请分段预约"]})
        return attrs
