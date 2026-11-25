from django.conf import settings
from django.db import models
from simple_history.models import HistoricalRecords

from core.files import stored_name


class RecordStatus(models.TextChoices):
    DRAFT = "draft", "草稿"
    SUBMITTED = "submitted", "已提交"


class Experiment(models.Model):
    """实验与原始数据：一次采集的背景（设备、试件、参数、步骤、现场照片）和这次的原始数据文件。
    个人数据：本人 + 本组导师可见；提交后锁定，导师可退回为草稿；关联了项目并提交后，项目当前成员也可见。"""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="操作人", on_delete=models.PROTECT, related_name="experiments")
    project = models.ForeignKey(
        "projects.Project", verbose_name="项目", null=True, blank=True, on_delete=models.PROTECT, related_name="experiments"
    )
    title = models.CharField("实验名称", max_length=200)
    date = models.DateField("实验日期")
    equipment_item = models.ForeignKey(
        "equipment.Equipment", verbose_name="台账设备", null=True, blank=True, on_delete=models.PROTECT, related_name="experiments"
    )
    # Free text for equipment outside the inventory and for records written before it existed.
    equipment = models.CharField("设备说明", max_length=200, blank=True)
    specimen = models.CharField("试件", max_length=200, blank=True)
    specimen_items = models.ManyToManyField(
        "specimens.Specimen", verbose_name="台账试件", blank=True, related_name="experiments"
    )
    params = models.JSONField("实验参数", default=dict, blank=True)
    steps = models.TextField("步骤与现场记录", blank=True)
    anomalies = models.TextField("异常情况", blank=True)
    # This record's own raw data files, created with the record. Uploading needs no separate dataset any more.
    dataset = models.OneToOneField(
        "datasets.Dataset", verbose_name="原始数据", null=True, blank=True, on_delete=models.PROTECT, related_name="raw_of"
    )
    # Datasets linked before records held their own files (2026-11-25); kept and shown, no longer added in the pages.
    datasets = models.ManyToManyField("datasets.Dataset", verbose_name="关联数据", blank=True, related_name="experiments")
    status = models.CharField("状态", max_length=16, choices=RecordStatus.choices, default=RecordStatus.DRAFT)
    submitted_at = models.DateTimeField("提交时间", null=True, blank=True)
    # {dataset id: version code} pinned on submit, cleared when returned to draft. See datasets/versions.py.
    data_versions = models.JSONField("引用的数据版本", default=dict, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = verbose_name_plural = "实验与原始数据"
        ordering = ["-date", "-id"]

    @property
    def code(self):
        return f"EX-{self.created_at:%Y}-{self.pk:04d}" if self.pk and self.created_at else ""

    def cited_datasets(self):
        return list({d.pk: d for d in [self.dataset, *self.datasets.all()] if d is not None}.values())

    def __str__(self):
        return f"{self.code} {self.title}"


def photo_upload_to(instance, filename):
    return stored_name("experiment-photos", filename)


class ExperimentPhoto(models.Model):
    """实验的现场照片、现象附图。本人在草稿时增删，提交后随记录锁定；看得到实验的人都看得到。"""

    experiment = models.ForeignKey(Experiment, verbose_name="实验", on_delete=models.CASCADE, related_name="photos")
    file = models.FileField("文件", upload_to=photo_upload_to, max_length=300)
    name = models.CharField("文件名", max_length=255)
    size = models.PositiveBigIntegerField("大小")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="上传人", on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = verbose_name_plural = "实验照片"
        ordering = ["created_at", "id"]

    def __str__(self):
        return self.name


class ProcessingRun(models.Model):
    """数据处理：引用的原始数据（实验）+ 算法（脚本文件、git 仓库或软件/方法说明）+ 参数 + 结果文件与结论。
    提交时固定所引用数据的版本，别人拿到记录能复现结果。

    脚本文件和结果文件各是一个数据集（script_dataset / output_dataset），随记录创建，在本页上传。"""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="提交人", on_delete=models.PROTECT, related_name="processing_runs")
    project = models.ForeignKey(
        "projects.Project", verbose_name="项目", null=True, blank=True, on_delete=models.PROTECT, related_name="processing_runs"
    )
    title = models.CharField("任务名称", max_length=200)
    experiments = models.ManyToManyField(Experiment, verbose_name="引用的原始数据", blank=True, related_name="runs")
    # Input datasets cited before runs cited experiments (2026-11-25); kept and shown, no longer added in the pages.
    inputs = models.ManyToManyField("datasets.Dataset", verbose_name="输入数据", blank=True, related_name="used_by_runs")
    script_dataset = models.ForeignKey(
        "datasets.Dataset", verbose_name="脚本文件", null=True, blank=True, on_delete=models.PROTECT, related_name="script_of_runs"
    )
    script_repo = models.CharField("git 仓库地址", max_length=500, blank=True)
    script_commit = models.CharField("git commit", max_length=64, blank=True)
    script_path = models.CharField("入口脚本", max_length=300, blank=True)
    # For processing done in Origin, Excel or an instrument's software: what was done, step by step.
    method = models.TextField("软件/方法说明", blank=True)
    method_version = models.CharField("方法版本", max_length=50, blank=True)
    params = models.JSONField("处理参数", default=dict, blank=True)
    environment = models.CharField("运行环境", max_length=200, blank=True)
    output_dataset = models.ForeignKey(
        "datasets.Dataset", verbose_name="结果文件", null=True, blank=True, on_delete=models.PROTECT, related_name="produced_by_runs"
    )
    conclusion = models.TextField("结论", blank=True)
    status = models.CharField("状态", max_length=16, choices=RecordStatus.choices, default=RecordStatus.DRAFT)
    submitted_at = models.DateTimeField("提交时间", null=True, blank=True)
    # {dataset id: version code} pinned on submit, cleared when returned to draft. See datasets/versions.py.
    data_versions = models.JSONField("引用的数据版本", default=dict, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = verbose_name_plural = "数据处理"
        ordering = ["-created_at"]

    @property
    def code(self):
        return f"RUN-{self.created_at:%Y}-{self.pk:04d}" if self.pk and self.created_at else ""

    def cited_datasets(self):
        """Pinned on submit: the cited experiments' raw data, the script and result files, earlier input datasets."""
        cited = [*self.inputs.all(), self.script_dataset, self.output_dataset]
        for experiment in self.experiments.select_related("dataset").prefetch_related("datasets"):
            cited += experiment.cited_datasets()
        return list({d.pk: d for d in cited if d is not None}.values())

    def __str__(self):
        return f"{self.code} {self.title}"
