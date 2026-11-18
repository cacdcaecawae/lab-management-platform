from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from simple_history.models import HistoricalRecords

from core.files import stored_name


def doc_upload_to(instance, filename):
    return stored_name("knowledge", filename)


class Doc(models.Model):
    """知识库文档。组内公开：本组全员可看、可新建；作者和管理员修改、上传新版本；只有管理员删除。"""

    class Category(models.TextChoices):
        SDK = "sdk", "设备 SDK"
        MANUAL = "manual", "使用手册"
        EXPERIENCE = "experience", "调试经验"
        PROCEDURE = "procedure", "操作规范"
        TEMPLATE = "template", "代码模板"

    group = models.ForeignKey("accounts.ResearchGroup", verbose_name="课题组", on_delete=models.PROTECT, related_name="docs")
    title = models.CharField("标题", max_length=200)
    category = models.CharField("分类", max_length=16, choices=Category.choices)
    equipment = models.ForeignKey(
        "equipment.Equipment", verbose_name="关联设备", null=True, blank=True, on_delete=models.SET_NULL, related_name="docs"
    )
    tags = ArrayField(models.CharField(max_length=30), verbose_name="标签", default=list, blank=True)
    description = models.TextField("说明", blank=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="作者", on_delete=models.PROTECT, related_name="docs")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = verbose_name_plural = "知识库文档"
        ordering = ["-updated_at", "-id"]

    def __str__(self):
        return self.title


class DocVersion(models.Model):
    """文档的一个文件版本。新版本不覆盖旧版本，版本号从 1 起逐个加一。"""

    doc = models.ForeignKey(Doc, verbose_name="文档", on_delete=models.CASCADE, related_name="versions")
    number = models.PositiveIntegerField("版本号")
    file = models.FileField("文件", upload_to=doc_upload_to, max_length=300)
    name = models.CharField("文件名", max_length=255)
    size = models.PositiveBigIntegerField("大小")
    sha256 = models.CharField("SHA256", max_length=64)
    note = models.CharField("本版说明", max_length=200, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="上传人", on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = verbose_name_plural = "文档版本"
        ordering = ["-number"]
        constraints = [models.UniqueConstraint(fields=["doc", "number"], name="uniq_doc_version_number")]

    def __str__(self):
        return f"{self.doc} v{self.number}"
