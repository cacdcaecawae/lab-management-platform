from django.conf import settings
from django.db import models
from django.db.models import Q


class Consumable(models.Model):
    """耗材品类。组内公开；只有本组管理员能新建和修改。库存不入库，由流水汇总。"""

    group = models.ForeignKey("accounts.ResearchGroup", verbose_name="课题组", on_delete=models.PROTECT, related_name="consumables")
    name = models.CharField("名称", max_length=100)
    spec = models.CharField("规格", max_length=100, blank=True)
    unit = models.CharField("单位", max_length=20, default="个")
    location = models.CharField("存放位置", max_length=200, blank=True)
    safety_stock = models.PositiveIntegerField("安全库存", default=0)
    notes = models.TextField("备注", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = verbose_name_plural = "耗材"
        ordering = ["name", "spec"]
        constraints = [models.UniqueConstraint(fields=["group", "name", "spec"], name="uniq_consumable_per_group")]

    def __str__(self):
        return f"{self.name} {self.spec}".strip()


class StockTxn(models.Model):
    """出入库流水，只增不改。quantity 带符号：入库、退回为正，领用为负，盘点调整为实际与账面的差。"""

    class Kind(models.TextChoices):
        IN = "in", "入库"
        OUT = "out", "领用"
        RETURN = "return", "退回"
        ADJUST = "adjust", "盘点调整"

    consumable = models.ForeignKey(Consumable, verbose_name="耗材", on_delete=models.PROTECT, related_name="txns")
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
        constraints = [models.CheckConstraint(condition=~Q(quantity=0), name="stock_txn_nonzero")]
