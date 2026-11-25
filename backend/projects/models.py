from django.conf import settings
from django.db import models

from core.files import stored_name


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


def project_file_upload_to(instance, filename):
    return stored_name("projects", filename)


class ProjectFile(models.Model):
    """项目文件 / 阶段资料（开题、中期、结题报告等）。组内公开；项目成员上传。"""

    project = models.ForeignKey(Project, verbose_name="项目", on_delete=models.CASCADE, related_name="files")
    file = models.FileField("文件", upload_to=project_file_upload_to, max_length=300)
    name = models.CharField("文件名", max_length=255)
    size = models.PositiveBigIntegerField("大小")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="上传人", on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = verbose_name_plural = "项目文件"
        ordering = ["created_at", "id"]

    def __str__(self):
        return self.name


class Milestone(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="milestones")
    title = models.CharField(max_length=200)
    due_date = models.DateField(null=True, blank=True)
    done_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["id", "project"], name="milestone_id_project_key")]


class Task(models.Model):
    class Status(models.TextChoices):
        TODO = "todo", "待办"
        DOING = "doing", "进行中"
        DONE = "done", "完成"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="tasks")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    assignee_name = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.TODO)
    milestone = models.ForeignKey(Milestone, null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks")
    due_date = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["project", "status", "due_date"]), models.Index(fields=["assignee", "status", "due_date"])]


class TaskChange(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="history")
    actor_name = models.CharField(max_length=200)
    changes = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]
