from django.contrib.auth.models import AbstractUser
from django.db import models

from core.files import stored_name


def avatar_upload_to(instance, filename):
    return stored_name("avatars", filename)


class ResearchGroup(models.Model):
    """课题组。每个成员属于一个课题组；管理员和导师只能看到本组数据。"""

    name = models.CharField("名称", max_length=100, unique=True)
    finance_email = models.EmailField("财务邮箱", blank=True, help_text="每周一收到“已交财务、尚未到账”的报销提醒")
    signup_code = models.CharField("学生注册码", max_length=16, blank=True)  # empty: the registration link is off
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
    wechat = models.CharField("微信号", max_length=50, blank=True)
    avatar = models.FileField("头像", upload_to=avatar_upload_to, max_length=300, blank=True)
    must_change_password = models.BooleanField("需修改初始密码", default=True)
    # A student who registered through the group's link; inactive until a manager approves (or deletes) it.
    pending = models.BooleanField("待审核", default=False)

    class Meta:
        verbose_name = verbose_name_plural = "成员"
        constraints = [
            # Managers approve or delete pending accounts, so only an inactive student may be one.
            models.CheckConstraint(
                condition=models.Q(pending=False) | models.Q(is_active=False, role="student"), name="pending_is_inactive_student",
            ),
        ]

    def save(self, *args, **kwargs):
        # Switched on (系统管理, /admin/) or given another role by ops: no longer an application for the managers.
        if self.pending and (self.is_active or self.role != self.Role.STUDENT):
            self.pending = False
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = {*kwargs["update_fields"], "pending"}
        super().save(*args, **kwargs)

    @property
    def is_supervisor(self):
        return self.role in (self.Role.MANAGER, self.Role.ADVISOR)

    @property
    def display_name(self):
        return self.name or self.username

    def __str__(self):
        return f"{self.display_name} ({self.username})"


class LoginEvent(models.Model):
    """Minimal account login outcomes; a throttled row means at least one rejection in that minute."""

    class Outcome(models.TextChoices):
        SUCCESS = "success", "登录成功"
        FAILED = "failed", "认证失败"
        THROTTLED = "throttled", "限流发生分钟"

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    ip = models.GenericIPAddressField(null=True, blank=True)
    outcome = models.CharField(max_length=12, choices=Outcome.choices)
    at = models.DateTimeField(db_index=True)

    class Meta:
        ordering = ["-at", "-pk"]
        indexes = [models.Index(fields=["outcome", "at"], name="login_outcome_at_idx")]
        constraints = [
            models.UniqueConstraint(
                fields=["at"], condition=models.Q(outcome="throttled"), name="login_one_throttle_per_minute",
            ),
        ]
