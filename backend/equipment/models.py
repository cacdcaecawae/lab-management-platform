import uuid
from pathlib import Path

from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeBoundary, RangeOperators
from django.db import models
from django.db.models import F, Func, Q
from django.utils import timezone
from simple_history.models import HistoricalRecords


class Equipment(models.Model):
    """设备台账。组内公开；只有本组管理员能新建和修改。不删除，报废用"停用"。

    "使用中"不是状态：由"当前时间落在某个未取消的预约里"推算（见 EquipmentViewSet）。"""

    class Status(models.TextChoices):
        AVAILABLE = "available", "可用"
        NEEDS_CHECK = "needs_check", "待检查"
        REPAIR = "repair", "维修"
        RETIRED = "retired", "停用"

    group = models.ForeignKey("accounts.ResearchGroup", verbose_name="课题组", on_delete=models.PROTECT, related_name="equipment")
    code = models.CharField("设备编号", max_length=50)
    name = models.CharField("名称", max_length=200)
    model = models.CharField("型号", max_length=200, blank=True)
    category = models.CharField("类别", max_length=50, blank=True)
    location = models.CharField("存放位置", max_length=200, blank=True)
    custodian = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="保管人", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    status = models.CharField("状态", max_length=16, choices=Status.choices, default=Status.AVAILABLE)
    purchase_date = models.DateField("购置日期", null=True, blank=True)
    calibration_due = models.DateField("下次校准日期", null=True, blank=True)
    notes = models.TextField("备注", blank=True)
    purchase = models.ForeignKey(
        "procurement.PurchaseRequest", verbose_name="采购申请", null=True, blank=True, on_delete=models.PROTECT,
        related_name="equipment",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = verbose_name_plural = "设备"
        ordering = ["code"]
        constraints = [models.UniqueConstraint(fields=["group", "code"], name="uniq_equipment_code_per_group")]

    def __str__(self):
        return f"{self.code} {self.name}"


class TsTzRange(Func):
    function = "TSTZRANGE"
    output_field = DateTimeRangeField()


class Booking(models.Model):
    """设备预约。先到先得，不审批；取消只记 cancelled_at，不删除。

    同一设备未取消的预约时段不能重叠，由数据库排他约束保证（需要 btree_gist 扩展，见 0001 迁移）。
    区间为 [start, end)：上一个预约的结束时刻可以是下一个的开始时刻。"""

    class Kind(models.TextChoices):
        USE = "use", "使用"
        MAINTENANCE = "maintenance", "维护"

    equipment = models.ForeignKey(Equipment, verbose_name="设备", on_delete=models.PROTECT, related_name="bookings")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="预约人", on_delete=models.PROTECT, related_name="bookings")
    project = models.ForeignKey(
        "projects.Project", verbose_name="项目", null=True, blank=True, on_delete=models.PROTECT, related_name="bookings"
    )
    kind = models.CharField("类型", max_length=16, choices=Kind.choices, default=Kind.USE)
    start_at = models.DateTimeField("开始时间")
    end_at = models.DateTimeField("结束时间")
    purpose = models.CharField("用途", max_length=200, blank=True)
    cancelled_at = models.DateTimeField("取消时间", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = verbose_name_plural = "设备预约"
        ordering = ["start_at", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(end_at__gt=F("start_at")), name="booking_ends_after_start"),
            ExclusionConstraint(
                name="no_overlapping_bookings",
                expressions=[
                    (TsTzRange("start_at", "end_at", RangeBoundary()), RangeOperators.OVERLAPS),
                    ("equipment", RangeOperators.EQUAL),
                ],
                condition=Q(cancelled_at__isnull=True),
            ),
        ]

    def __str__(self):
        return f"{self.equipment} {timezone.localtime(self.start_at):%Y-%m-%d %H:%M}"


def usage_photo_upload_to(instance, filename):
    # Server-generated name: the client's file name never becomes a storage path.
    return f"usage-photos/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"


class UsageReport(models.Model):
    """使用登记：预约人在使用开始后登记一次。异常时设备自动转为"待检查"。"""

    class Condition(models.TextChoices):
        NORMAL = "normal", "正常"
        ABNORMAL = "abnormal", "异常"

    booking = models.OneToOneField(Booking, verbose_name="预约", on_delete=models.PROTECT, related_name="report")
    condition = models.CharField("设备状况", max_length=16, choices=Condition.choices)
    description = models.TextField("说明", blank=True)
    photo = models.FileField("照片", upload_to=usage_photo_upload_to, max_length=300, blank=True)
    photo_size = models.PositiveBigIntegerField("照片字节数", null=True, blank=True, editable=False)
    photo_uploaded_at = models.DateTimeField("当前照片上传时间", null=True, blank=True, editable=False)
    reported_at = models.DateTimeField("登记时间", auto_now_add=True)

    class Meta:
        verbose_name = verbose_name_plural = "使用登记"
