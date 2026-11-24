import uuid
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.db import models
from django.db.models import Q
from simple_history.models import HistoricalRecords


def money(verbose_name):
    """Amounts in yuan (RMB), never floats."""
    return models.DecimalField(verbose_name, max_digits=12, decimal_places=2)


class Fund(models.Model):
    """经费来源。组内公开（填单时要选），只有本组管理员维护。停用后不能再选，旧单据照常显示。"""

    group = models.ForeignKey("accounts.ResearchGroup", verbose_name="课题组", on_delete=models.PROTECT, related_name="funds")
    name = models.CharField("名称", max_length=100)
    code = models.CharField("经费号", max_length=50)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="负责人", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    active = models.BooleanField("可用", default=True)
    notes = models.TextField("备注", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = verbose_name_plural = "经费来源"
        ordering = ["-active", "code"]
        constraints = [models.UniqueConstraint(fields=["group", "code"], name="uniq_fund_code_per_group")]

    def __str__(self):
        return f"{self.code} {self.name}"


class PurchaseRequest(models.Model):
    """采购申请。个人数据：本人和本组管理员、终审人可见（按 owner 的课题组隔离）。

    草稿 -> 待初审（管理员）-> 待终审（终审人）-> 已批准 -> 已采购 -> 已到货。管理员的申请跳过初审；
    终审人的申请由另一位终审人终审，组里没有别的终审人时初审通过即批准。退回回到草稿。批准后改了明细，重新进入审批。"""

    class Status(models.TextChoices):
        DRAFT = "draft", "草稿"
        PENDING_INITIAL = "pending_initial", "待初审"
        PENDING_FINAL = "pending_final", "待终审"
        APPROVED = "approved", "已批准"
        PURCHASED = "purchased", "已采购"
        ARRIVED = "arrived", "已到货"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="申请人", on_delete=models.PROTECT, related_name="purchases")
    fund = models.ForeignKey(Fund, verbose_name="经费来源", null=True, blank=True, on_delete=models.PROTECT, related_name="purchases")
    purpose = models.TextField("用途", blank=True)
    status = models.CharField("状态", max_length=16, choices=Status.choices, default=Status.DRAFT)
    submitted_at = models.DateTimeField("提交时间", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = verbose_name_plural = "采购申请"
        ordering = ["-created_at", "-id"]

    @property
    def code(self):
        return f"PR-{self.created_at:%Y}-{self.pk:04d}" if self.pk and self.created_at else ""

    @property
    def total(self):
        # Never stored, so it cannot drift from the items. Uses prefetched items when present.
        return sum((i.quantity * i.unit_price for i in self.items.all()), Decimal("0.00"))

    def __str__(self):
        return self.code


class PurchaseItem(models.Model):
    request = models.ForeignKey(PurchaseRequest, verbose_name="采购申请", on_delete=models.CASCADE, related_name="items")
    name = models.CharField("品名", max_length=200)
    spec = models.CharField("规格型号", max_length=200, blank=True)
    quantity = models.PositiveIntegerField("数量")
    unit_price = money("单价")
    link = models.URLField("链接", max_length=500, blank=True)

    class Meta:
        verbose_name = verbose_name_plural = "采购明细"
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="purchase_item_quantity_positive"),
            models.CheckConstraint(condition=Q(unit_price__gte=0), name="purchase_item_price_not_negative"),
        ]

    def __str__(self):
        return f"{self.name} x{self.quantity}"


class Approval(models.Model):
    """一步审批的记录，只增不改。total 是审批人当时看到的合计。"""

    class Stage(models.TextChoices):
        INITIAL = "initial", "初审"
        FINAL = "final", "终审"

    class Verdict(models.TextChoices):
        APPROVE = "approve", "通过"
        RETURN = "return", "退回修改"

    request = models.ForeignKey(PurchaseRequest, verbose_name="采购申请", on_delete=models.PROTECT, related_name="approvals")
    stage = models.CharField("环节", max_length=16, choices=Stage.choices)
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="审批人", on_delete=models.PROTECT, related_name="+")
    verdict = models.CharField("结论", max_length=16, choices=Verdict.choices)
    comment = models.TextField("意见", blank=True)
    total = money("审批时的合计")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = verbose_name_plural = "审批记录"
        ordering = ["created_at", "id"]


class Reimbursement(models.Model):
    """报销。个人数据。不审批，只记录：待提交 -> 已交财务 -> 已到账，由本人或管理员推进。"""

    class Category(models.TextChoices):
        EQUIPMENT = "equipment", "设备"
        CONSUMABLE = "consumable", "耗材"
        TRAVEL = "travel", "差旅"
        AI_TOOL = "ai_tool", "AI 工具"
        OTHER = "other", "其他"

    class Status(models.TextChoices):
        PENDING = "pending", "待提交"
        SUBMITTED = "submitted", "已交财务"
        PAID = "paid", "已到账"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="报销人", on_delete=models.PROTECT, related_name="reimbursements"
    )
    fund = models.ForeignKey(Fund, verbose_name="经费来源", on_delete=models.PROTECT, related_name="reimbursements")
    purchase = models.ForeignKey(
        PurchaseRequest, verbose_name="采购申请", null=True, blank=True, on_delete=models.PROTECT, related_name="reimbursements"
    )
    category = models.CharField("类别", max_length=16, choices=Category.choices)
    amount = money("金额")
    occurred_on = models.DateField("发生日期")
    description = models.CharField("说明", max_length=200, blank=True)
    status = models.CharField("状态", max_length=16, choices=Status.choices, default=Status.PENDING)
    submitted_at = models.DateTimeField("交财务时间", null=True, blank=True)
    paid_at = models.DateTimeField("到账时间", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = verbose_name_plural = "报销"
        ordering = ["-occurred_on", "-id"]
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name="reimbursement_amount_positive")]

    @property
    def code(self):
        return f"RB-{self.created_at:%Y}-{self.pk:04d}" if self.pk and self.created_at else ""

    def __str__(self):
        return self.code


def attachment_upload_to(instance, filename):
    # Server-generated name: the client's file name never becomes a storage path (it is kept in `name`).
    return f"procurement/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"


class Attachment(models.Model):
    """报价单、发票等附件，属于一张采购申请或一条报销。下载走带权限检查的接口。"""

    class Kind(models.TextChoices):
        QUOTE = "quote", "报价单"
        INVOICE = "invoice", "发票"
        OTHER = "other", "其他"

    purchase = models.ForeignKey(
        PurchaseRequest, verbose_name="采购申请", null=True, blank=True, on_delete=models.CASCADE, related_name="attachments"
    )
    reimbursement = models.ForeignKey(
        Reimbursement, verbose_name="报销", null=True, blank=True, on_delete=models.CASCADE, related_name="attachments"
    )
    kind = models.CharField("类型", max_length=16, choices=Kind.choices, default=Kind.OTHER)
    file = models.FileField("文件", upload_to=attachment_upload_to, max_length=300)
    name = models.CharField("文件名", max_length=200)
    size = models.PositiveBigIntegerField("大小")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="上传人", on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = verbose_name_plural = "附件"
        ordering = ["created_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(purchase__isnull=False, reimbursement__isnull=True)
                | Q(purchase__isnull=True, reimbursement__isnull=False),
                name="attachment_has_one_parent",
            )
        ]

    def __str__(self):
        return self.name
