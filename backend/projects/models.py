from django.conf import settings
from django.db import models


class Project(models.Model):
    """研究项目（课题）。组内公开：同组成员都能看到。经费项目是另一个概念，在第三期单独建表。"""

    class Status(models.TextChoices):
        ACTIVE = "active", "进行中"
        CLOSED = "closed", "已结束"

    group = models.ForeignKey("accounts.ResearchGroup", verbose_name="课题组", on_delete=models.PROTECT, related_name="projects")
    name = models.CharField("项目名称", max_length=200)
    leader = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="负责人", on_delete=models.PROTECT, related_name="led_projects")
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, verbose_name="成员", blank=True, related_name="projects")
    stage = models.CharField("当前阶段", max_length=100, blank=True)
    status = models.CharField("状态", max_length=16, choices=Status.choices, default=Status.ACTIVE)
    description = models.TextField("说明", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = verbose_name_plural = "项目"
        ordering = ["-updated_at"]
        constraints = [models.UniqueConstraint(fields=["group", "name"], name="uniq_project_name_per_group")]

    def __str__(self):
        return self.name


class ProjectLog(models.Model):
    """项目进展记录：日期 + 已完成的工作。"""

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="logs")
    date = models.DateField("日期")
    content = models.TextField("进展内容")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="记录人", on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = verbose_name_plural = "项目进展"
        ordering = ["-date", "-id"]
