from django.conf import settings
from django.db import models
from simple_history.models import HistoricalRecords

from core.files import stored_name


def fulltext_upload_to(instance, filename):
    return stored_name("achievements", filename)


class Achievement(models.Model):
    """成果：论文、专利、获奖、软著。组内公开；全员可以登记；登记人、署名的本组成员和管理员修改；只有管理员删除。"""

    class Type(models.TextChoices):
        PAPER = "paper", "论文"
        PATENT = "patent", "专利"
        AWARD = "award", "获奖"
        SOFTWARE = "software", "软著"

    class Status(models.TextChoices):
        SUBMITTED = "submitted", "投稿中"
        ACCEPTED = "accepted", "已录用"
        PUBLISHED = "published", "已发表"
        FILED = "filed", "申请中"
        GRANTED = "granted", "已授权"
        AWARDED = "awarded", "已获奖"
        REGISTERED = "registered", "已登记"

    group = models.ForeignKey(
        "accounts.ResearchGroup", verbose_name="课题组", on_delete=models.PROTECT, related_name="achievements"
    )
    type = models.CharField("类型", max_length=16, choices=Type.choices)
    title = models.CharField("标题", max_length=300)
    authors = models.CharField("作者（按署名）", max_length=500)
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, verbose_name="本组成员", blank=True, related_name="achievements")
    venue = models.CharField("出处 / 编号", max_length=300, blank=True, help_text="期刊或会议；专利授权号；奖项和等级；软著登记号")
    date = models.DateField("日期")
    status = models.CharField("状态", max_length=16, choices=Status.choices)
    link = models.CharField("DOI / 链接", max_length=300, blank=True)
    fulltext = models.FileField("全文", upload_to=fulltext_upload_to, max_length=300, blank=True)
    fulltext_name = models.CharField("全文文件名", max_length=255, blank=True)
    notes = models.TextField("备注", blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="登记人", on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords(excluded_fields=["fulltext"])

    class Meta:
        verbose_name = verbose_name_plural = "成果"
        ordering = ["-date", "-id"]

    def __str__(self):
        return self.title


S = Achievement.Status
STATUSES = {
    Achievement.Type.PAPER: [S.SUBMITTED, S.ACCEPTED, S.PUBLISHED],
    Achievement.Type.PATENT: [S.FILED, S.GRANTED],
    Achievement.Type.AWARD: [S.AWARDED],
    Achievement.Type.SOFTWARE: [S.REGISTERED],
}
