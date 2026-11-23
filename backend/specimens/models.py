from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from simple_history.models import HistoricalRecords

from core.files import stored_name


def loan_photo_upload_to(instance, filename):
    return stored_name("specimens", filename)


class Specimen(models.Model):
    """试样与标准件台账：标准试块、对比试块、试样等。组内公开；只有本组管理员能新建和修改。不删除，不再用的改为"停用"。

    缺陷参数可能是盲测的真值：defects_public 为假时只有管理员和导师能看到（SpecimenSerializer）。
    "借出"不是状态：由是否有未归还的借用推算。"""

    class Kind(models.TextChoices):
        STANDARD = "standard", "标准试块"
        REFERENCE = "reference", "对比试块"
        SAMPLE = "sample", "试样"
        OTHER = "other", "其他"

    class Status(models.TextChoices):
        AVAILABLE = "available", "可用"
        DAMAGED = "damaged", "损坏"
        RETIRED = "retired", "停用"

    group = models.ForeignKey("accounts.ResearchGroup", verbose_name="课题组", on_delete=models.PROTECT, related_name="specimens")
    code = models.CharField("编号", max_length=50)
    name = models.CharField("名称", max_length=200)
    kind = models.CharField("类别", max_length=16, choices=Kind.choices, default=Kind.SAMPLE)
    material = models.CharField("材料", max_length=100, blank=True)
    dimensions = models.CharField("尺寸", max_length=200, blank=True)
    location = models.CharField("存放位置", max_length=200, blank=True)
    custodian = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="保管人", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    status = models.CharField("状态", max_length=16, choices=Status.choices, default=Status.AVAILABLE)
    defects_public = models.BooleanField("缺陷参数对学生公开", default=False)
    notes = models.TextField("备注", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()  # specimen fields only: hidden defect values never reach the history

    class Meta:
        verbose_name = verbose_name_plural = "试样与标准件"
        ordering = ["code"]
        constraints = [models.UniqueConstraint(fields=["group", "code"], name="uniq_specimen_code_per_group")]

    def __str__(self):
        return f"{self.code} {self.name}"


class Defect(models.Model):
    """试件上的一个人工缺陷或已知缺陷。随试件一起编辑：整份列表替换。"""

    class Kind(models.TextChoices):
        FLAT_BOTTOM_HOLE = "fbh", "平底孔"
        SIDE_DRILLED_HOLE = "sdh", "横通孔"
        NOTCH = "notch", "刻槽"
        CRACK = "crack", "裂纹"
        DELAMINATION = "delamination", "分层"
        OTHER = "other", "其他"

    specimen = models.ForeignKey(Specimen, on_delete=models.CASCADE, related_name="defects")
    kind = models.CharField("类型", max_length=16, choices=Kind.choices)
    size_mm = models.DecimalField("尺寸（mm）", max_digits=8, decimal_places=2, null=True, blank=True)  # 孔径、槽长等
    depth_mm = models.DecimalField("埋深（mm）", max_digits=8, decimal_places=2, null=True, blank=True)
    position = models.CharField("位置", max_length=200, blank=True)
    note = models.CharField("备注", max_length=200, blank=True)

    class Meta:
        verbose_name = verbose_name_plural = "缺陷"
        ordering = ["id"]


class SpecimenLoan(models.Model):
    """借用登记：借出时新建，归还时填 returned_at。同一试件同时只有一条未归还的借用，由数据库约束保证。"""

    specimen = models.ForeignKey(Specimen, verbose_name="试件", on_delete=models.PROTECT, related_name="loans")
    borrower = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="借用人", on_delete=models.PROTECT, related_name="+")
    project = models.ForeignKey(
        "projects.Project", verbose_name="项目", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    purpose = models.CharField("用途", max_length=200, blank=True)
    due_date = models.DateField("预计归还日期", null=True, blank=True)
    borrowed_at = models.DateTimeField("借出时间", default=timezone.now)
    returned_at = models.DateTimeField("归还时间", null=True, blank=True)
    returned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="登记归还的人", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    return_note = models.CharField("归还说明", max_length=200, blank=True)
    return_location = models.CharField("放回位置", max_length=200, blank=True)
    return_photo = models.FileField("归还照片", upload_to=loan_photo_upload_to, max_length=300, blank=True)
    return_photo_size = models.BigIntegerField("归还照片大小", null=True, blank=True)
    return_photo_uploaded_at = models.DateTimeField("归还照片上传时间", null=True, blank=True)

    class Meta:
        verbose_name = verbose_name_plural = "借用"
        ordering = ["-borrowed_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["specimen"], condition=Q(returned_at__isnull=True), name="one_open_loan_per_specimen")
        ]
