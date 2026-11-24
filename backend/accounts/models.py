from django.contrib.auth.models import AbstractUser
from django.contrib.postgres.fields import ArrayField
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
    """username 即学号或工号。first_name / last_name 不使用，姓名存在 name。

    What one may do comes from the base role and two tags (.agents/notes/implemented/architecture/
    2026-11-23-roles-and-identity.md): advisors see and review the group's research records, managers run its affairs,
    approvers do the final review of purchases. Identity, year, graduation and tags only describe the person."""

    class Role(models.TextChoices):
        STUDENT = "student", "学生"
        ADVISOR = "advisor", "导师"

    class Identity(models.TextChoices):
        TEACHER = "teacher", "教师"
        POSTDOC = "postdoc", "博士后"
        PHD = "phd", "博士生"
        MASTER = "master", "硕士生"
        UNDERGRADUATE = "undergraduate", "本科生"
        ASSISTANT = "assistant", "科研助理"

    group = models.ForeignKey(
        ResearchGroup, verbose_name="课题组", null=True, blank=True, on_delete=models.PROTECT, related_name="members"
    )
    role = models.CharField("基础角色", max_length=16, choices=Role.choices, default=Role.STUDENT)
    is_manager = models.BooleanField("管理员", default=False)
    is_approver = models.BooleanField("终审人", default=False)
    identity = models.CharField("身份", max_length=16, choices=Identity.choices, blank=True)
    enrollment_year = models.PositiveSmallIntegerField("入学年份", null=True, blank=True)
    graduated = models.BooleanField("已毕业", default=False)  # read with is_active: see member_status
    tags = ArrayField(models.CharField(max_length=20), verbose_name="词条", default=list, blank=True)
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
        changed = set()
        # Switched on (系统管理, /admin/) or given another role by ops: no longer an application for the managers.
        if self.pending and (self.is_active or self.role != self.Role.STUDENT):
            self.pending = False
            changed.add("pending")
        if self.is_active and self.graduated:  # back in the group (e.g. a master's graduate starting a PhD)
            self.graduated = False
            changed.add("graduated")
        if changed and kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = {*kwargs["update_fields"], *changed}
        super().save(*args, **kwargs)

    @property
    def is_advisor(self):
        return self.role == self.Role.ADVISOR

    @property
    def is_supervisor(self):
        """导师或管理员: new projects and their leaders, blind defect sizes, usage and storage statistics, members'
        contact details. Research records need the advisor role, purchases a tag (core.permissions)."""
        return self.is_advisor or self.is_manager

    @property
    def member_status(self):
        """在籍 / 已毕业 / 已停用: only active accounts sign in."""
        return "active" if self.is_active else "graduated" if self.graduated else "disabled"

    @property
    def audiences(self):
        """Notifications sent to a role or tag (core.notifications.AUDIENCES) that this user reads."""
        return ["", *(["advisor"] if self.is_advisor else []), *(["manager"] if self.is_manager else []),
                *(["approver"] if self.is_approver else [])]

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
