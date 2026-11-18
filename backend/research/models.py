from django.conf import settings
from django.db import models
from simple_history.models import HistoricalRecords


class RecordStatus(models.TextChoices):
    DRAFT = "draft", "草稿"
    SUBMITTED = "submitted", "已提交"


class Experiment(models.Model):
    """实验记录。个人数据：本人 + 本组管理员/导师可见。提交后锁定，管理员/导师可退回为草稿。"""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="操作人", on_delete=models.PROTECT, related_name="experiments")
    project = models.ForeignKey("projects.Project", verbose_name="项目", on_delete=models.PROTECT, related_name="experiments")
    title = models.CharField("实验名称", max_length=200)
    date = models.DateField("实验日期")
    equipment_item = models.ForeignKey(
        "equipment.Equipment", verbose_name="台账设备", null=True, blank=True, on_delete=models.PROTECT, related_name="experiments"
    )
    # Free text for equipment outside the inventory and for records written before it existed.
    equipment = models.CharField("设备说明", max_length=200, blank=True)
    specimen = models.CharField("试件", max_length=200, blank=True)
    params = models.JSONField("实验参数", default=dict, blank=True)
    steps = models.TextField("步骤与现场记录", blank=True)
    anomalies = models.TextField("异常情况", blank=True)
    datasets = models.ManyToManyField("datasets.Dataset", verbose_name="关联数据", blank=True, related_name="experiments")
    status = models.CharField("状态", max_length=16, choices=RecordStatus.choices, default=RecordStatus.DRAFT)
    submitted_at = models.DateTimeField("提交时间", null=True, blank=True)
    # {dataset id: version code} pinned on submit, cleared when returned to draft. See datasets/versions.py.
    data_versions = models.JSONField("引用的数据版本", default=dict, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = verbose_name_plural = "实验记录"
        ordering = ["-date", "-id"]

    @property
    def code(self):
        return f"EX-{self.created_at:%Y}-{self.pk:04d}" if self.pk and self.created_at else ""

    def cited_datasets(self):
        return list(self.datasets.all())

    def __str__(self):
        return f"{self.code} {self.title}"


class ProcessingRun(models.Model):
    """数据处理记录：输入数据 + 脚本版本 + 参数 + 运行环境 + 结果。目标是别人拿到记录能复现结果。

    脚本二选一：上传为 kind=script 的数据集（script_dataset），或填写 git 仓库与 commit。
    结果文件登记为 kind=result 的数据集（output_dataset）。"""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="提交人", on_delete=models.PROTECT, related_name="processing_runs")
    project = models.ForeignKey("projects.Project", verbose_name="项目", on_delete=models.PROTECT, related_name="processing_runs")
    title = models.CharField("任务名称", max_length=200)
    inputs = models.ManyToManyField("datasets.Dataset", verbose_name="输入数据", blank=True, related_name="used_by_runs")
    script_dataset = models.ForeignKey(
        "datasets.Dataset", verbose_name="脚本文件", null=True, blank=True, on_delete=models.PROTECT, related_name="script_of_runs"
    )
    script_repo = models.CharField("git 仓库地址", max_length=500, blank=True)
    script_commit = models.CharField("git commit", max_length=64, blank=True)
    script_path = models.CharField("入口脚本", max_length=300, blank=True)
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
        verbose_name = verbose_name_plural = "数据处理记录"
        ordering = ["-created_at"]

    @property
    def code(self):
        return f"RUN-{self.created_at:%Y}-{self.pk:04d}" if self.pk and self.created_at else ""

    def cited_datasets(self):
        cited = [*self.inputs.all(), self.script_dataset, self.output_dataset]
        return list({d.pk: d for d in cited if d is not None}.values())

    def __str__(self):
        return f"{self.code} {self.title}"
