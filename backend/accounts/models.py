from django.contrib.auth.models import AbstractUser
from django.db import models


class ResearchGroup(models.Model):
    """课题组。每个成员属于一个课题组；管理员和导师只能看到本组数据。"""

    name = models.CharField("名称", max_length=100, unique=True)
    finance_email = models.EmailField("财务邮箱", blank=True, help_text="每周一收到“已交财务、尚未到账”的报销提醒")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = verbose_name_plural = "课题组"

    def __str__(self):
        return self.name


class User(AbstractUser):
    """username 即学号或工号。first_name / last_name 不使用，姓名存在 name。"""

    class Role(models.TextChoices):
        STUDENT = "student", "学生"
        MANAGER = "manager", "管理员"
        ADVISOR = "advisor", "导师"

    group = models.ForeignKey(
        ResearchGroup, verbose_name="课题组", null=True, blank=True, on_delete=models.PROTECT, related_name="members"
    )
    role = models.CharField("角色", max_length=16, choices=Role.choices, default=Role.STUDENT)
    name = models.CharField("姓名", max_length=50, blank=True)
    phone = models.CharField("联系电话", max_length=30, blank=True)
    research_direction = models.CharField("研究方向", max_length=100, blank=True)
    must_change_password = models.BooleanField("需修改初始密码", default=True)

    class Meta:
        verbose_name = verbose_name_plural = "成员"

    @property
    def is_supervisor(self):
        return self.role in (self.Role.MANAGER, self.Role.ADVISOR)

    @property
    def display_name(self):
        return self.name or self.username

    def __str__(self):
        return f"{self.display_name} ({self.username})"
