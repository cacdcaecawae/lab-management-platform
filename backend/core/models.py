from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from simple_history.models import HistoricalRecords


class SiteSettings(models.Model):
    """Platform-wide settings, edited by the ops account in 系统管理. A single row (pk=1); only mail so far."""

    class Security(models.TextChoices):
        SSL = "ssl", "SSL"
        STARTTLS = "starttls", "STARTTLS"
        NONE = "none", "不加密"

    mail_enabled = models.BooleanField("启用邮件", default=False)
    mail_host = models.CharField("SMTP 服务器", max_length=200, blank=True)
    mail_port = models.PositiveIntegerField("端口", default=465, validators=[MinValueValidator(1), MaxValueValidator(65535)])
    mail_security = models.CharField("加密方式", max_length=10, choices=Security.choices, default=Security.SSL)
    mail_username = models.CharField("账号", max_length=200, blank=True)
    # Stored as is: school mail gives a client authorization code that can be revoked and reissued.
    mail_password = models.CharField("授权码", max_length=200, blank=True)
    mail_from = models.EmailField("发件人地址", blank=True, help_text="留空时用账号作发件人")
    last_mail_error = models.TextField("最近一次发送失败的原因", blank=True)
    last_mail_error_at = models.DateTimeField("最近一次发送失败的时间", null=True, blank=True)
    history = HistoricalRecords(excluded_fields=["mail_password", "last_mail_error", "last_mail_error_at"])

    class Meta:
        verbose_name = verbose_name_plural = "系统设置"

    @classmethod
    def load(cls):
        return cls.objects.get_or_create(pk=1)[0]

    @property
    def sender(self):
        return self.mail_from or self.mail_username
