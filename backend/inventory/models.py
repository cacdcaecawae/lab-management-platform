from django.conf import settings
from django.db import models
from django.db.models import Q


class Consumable(models.Model):
    """耗材品类。组内公开；只有本组管理员能新建和修改。库存不入库，由流水汇总。"""

    group = models.ForeignKey("accounts.ResearchGroup", verbose_name="课题组", on_delete=models.PROTECT, related_name="consumables")
    name = models.CharField("名称", max_length=100)
    spec = models.CharField("规格", max_length=100, blank=True)
    unit = models.CharField("单位", max_length=20, default="个")
    category = models.CharField("分类", max_length=50, blank=True, db_default="")  # old binaries' INSERTs leave it out
    location = models.CharField("存放位置", max_length=200, blank=True)
    safety_stock = models.PositiveIntegerField("安全库存", default=0)
    tracks_batches = models.BooleanField("按批次管理", default=False, db_default=False)
    notes = models.TextField("备注", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = verbose_name_plural = "耗材"
        ordering = ["name", "spec"]
        constraints = [models.UniqueConstraint(fields=["group", "name", "spec"], name="uniq_consumable_per_group")]

    def __str__(self):
        return f"{self.name} {self.spec}".strip()


class Batch(models.Model):
    consumable = models.ForeignKey(Consumable, on_delete=models.PROTECT, related_name="batches")
    batch_no = models.CharField("批号", max_length=50)
    expires_on = models.DateField("有效期至", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["consumable", "batch_no"], name="uniq_inventory_batch")]
    def __str__(self):
        return self.batch_no


class StockTxn(models.Model):
    """出入库流水，只增不改。quantity 带符号：入库、退回为正，领用为负，盘点调整为实际与账面的差。"""

    class Kind(models.TextChoices):
        IN = "in", "入库"
        OUT = "out", "领用"
        RETURN = "return", "退回"
        ADJUST = "adjust", "盘点调整"
        ALLOCATION = "allocation", "批次期初分配"
        BATCH_MODE = "batch_mode", "批次管理变更"

    consumable = models.ForeignKey(Consumable, verbose_name="耗材", on_delete=models.PROTECT, related_name="txns")
    batch = models.ForeignKey(Batch, null=True, blank=True, on_delete=models.PROTECT, related_name="txns")
    kind = models.CharField("类型", max_length=16, choices=Kind.choices)
    quantity = models.IntegerField("数量")
    handler = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="经手人", on_delete=models.PROTECT, related_name="+")
    project = models.ForeignKey(
        "projects.Project", verbose_name="项目", null=True, blank=True, on_delete=models.PROTECT, related_name="stock_txns"
    )
    note = models.CharField("备注", max_length=200, blank=True)
    purchase = models.ForeignKey(
        "procurement.PurchaseRequest", verbose_name="采购申请", null=True, blank=True, on_delete=models.PROTECT,
        related_name="stock_txns",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = verbose_name_plural = "出入库流水"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(kind="batch_mode", quantity=0, batch__isnull=True)
                | (~Q(kind="batch_mode") & ~Q(quantity=0)),
                name="stock_txn_quantity_matches_kind",
            ),
        ]
