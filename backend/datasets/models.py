import uuid

from django.conf import settings
from django.db import models
from simple_history.models import HistoricalRecords


class Dataset(models.Model):
    """数据集：一批原始数据、脚本或处理结果。个人数据：本人 + 本组导师可见。

    文件入库后只读；修改过的数据作为新的数据集登记。"""

    class Kind(models.TextChoices):
        RAW = "raw", "原始数据"
        SCRIPT = "script", "脚本"
        RESULT = "result", "处理结果"
        OTHER = "other", "其他"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="创建人", on_delete=models.PROTECT, related_name="datasets")
    project = models.ForeignKey("projects.Project", verbose_name="项目", on_delete=models.PROTECT, related_name="datasets")
    name = models.CharField("名称", max_length=200)
    kind = models.CharField("类型", max_length=16, choices=Kind.choices, default=Kind.RAW)
    description = models.TextField("说明", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = verbose_name_plural = "数据集"
        ordering = ["-created_at"]

    @property
    def code(self):
        return f"DS-{self.created_at:%Y}-{self.pk:04d}" if self.pk and self.created_at else ""

    def __str__(self):
        return f"{self.code} {self.name}"


def datafile_upload_to(instance, filename):
    # Stored name is server-generated; the user's filename only lives in DataFile.name.
    return f"datasets/{instance.dataset_id}/{uuid.uuid4().hex}"


class DataFile(models.Model):
    """数据集中的一个文件。不可覆盖：同一数据集内文件名唯一；不提供修改接口。"""

    dataset = models.ForeignKey(Dataset, on_delete=models.PROTECT, related_name="files")
    name = models.CharField("文件名", max_length=255)
    file = models.FileField(upload_to=datafile_upload_to, max_length=300)
    size = models.BigIntegerField("大小（字节）")
    sha256 = models.CharField("SHA256", max_length=64)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="上传人", on_delete=models.PROTECT, related_name="+")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = verbose_name_plural = "数据文件"
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["dataset", "name"], name="uniq_file_name_per_dataset")]

    def __str__(self):
        return self.name


class DatasetSnapshot(models.Model):
    """数据集某个版本的文件清单（类似 git 的 tree）。记录提交时生成，文件清单相同的提交共用一份。见 datasets/versions.py。"""

    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name="snapshots")
    digest = models.CharField("版本码", max_length=64)
    files = models.ManyToManyField(DataFile, related_name="snapshots")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = verbose_name_plural = "数据集版本"
        constraints = [models.UniqueConstraint(fields=["dataset", "digest"], name="uniq_snapshot_per_dataset")]

    def __str__(self):
        return f"{self.dataset.code}@{self.digest[:12]}"
