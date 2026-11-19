from django.conf import settings
from django.db import models


class ReminderDelivery(models.Model):
    """Delivery ledger; never store addresses or the body here."""

    class State(models.TextChoices):
        SENDING = "sending", "发送中"
        SENT = "sent", "已接受"
        RETRYABLE = "retryable", "可重试"
        FAILED = "failed", "发送失败"
        UNCERTAIN = "uncertain", "结果不明"

    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    day = models.DateField()
    state = models.CharField(max_length=12, choices=State.choices, default=State.SENDING)
    attempts = models.PositiveSmallIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["recipient", "day"], name="one_daily_reminder_per_user")]
