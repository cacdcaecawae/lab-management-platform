from django.conf import settings
from django.db import models
from simple_history.models import HistoricalRecords


class WeeklyReport(models.Model):
    """周报：每人每周一份（week_start 为周一）。个人数据：本人 + 本组管理员/导师可见。

    状态：草稿 → 已提交 → 已阅 / 需补充；需补充时学生修改后再次提交。"""

    class Status(models.TextChoices):
        DRAFT = "draft", "草稿"
        SUBMITTED = "submitted", "已提交"
        NEEDS_REVISION = "needs_revision", "需补充"
        REVIEWED = "reviewed", "已阅"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="学生", on_delete=models.PROTECT, related_name="weekly_reports")
    week_start = models.DateField("周一日期")
    goals = models.TextField("本周目标", blank=True)
    done = models.TextField("完成工作", blank=True)
    findings = models.TextField("主要发现与证据", blank=True)
    next_plan = models.TextField("下周计划", blank=True)
    experiments = models.ManyToManyField("research.Experiment", verbose_name="关联实验", blank=True, related_name="weekly_reports")
    datasets = models.ManyToManyField("datasets.Dataset", verbose_name="关联数据", blank=True, related_name="weekly_reports")
    runs = models.ManyToManyField("research.ProcessingRun", verbose_name="关联处理记录", blank=True, related_name="weekly_reports")
    status = models.CharField("状态", max_length=16, choices=Status.choices, default=Status.DRAFT)
    submitted_at = models.DateTimeField("提交时间", null=True, blank=True)
    # {dataset id: version code} pinned on submit (again on every resubmit). See datasets/versions.py.
    data_versions = models.JSONField("引用的数据版本", default=dict, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = verbose_name_plural = "周报"
        ordering = ["-week_start", "owner_id"]
        constraints = [models.UniqueConstraint(fields=["owner", "week_start"], name="uniq_report_per_week")]

    def __str__(self):
        return f"{self.owner} {self.week_start}"

    def cited_datasets(self):
        return list(self.datasets.all())


class ReportFeedback(models.Model):
    """导师/管理员对周报的一次反馈。只增不改。"""

    class Verdict(models.TextChoices):
        REVIEWED = "reviewed", "已阅"
        NEEDS_REVISION = "needs_revision", "需补充"

    report = models.ForeignKey(WeeklyReport, on_delete=models.CASCADE, related_name="feedback")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="反馈人", on_delete=models.PROTECT, related_name="+")
    verdict = models.CharField("结论", max_length=16, choices=Verdict.choices)
    content = models.TextField("反馈内容", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = verbose_name_plural = "周报反馈"
        ordering = ["created_at"]
