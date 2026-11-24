from django.conf import settings
from django.db import models
from simple_history.models import HistoricalRecords

from core.files import stored_name


def meeting_file_upload_to(instance, filename):
    return stored_name("meetings", filename)


class Meeting(models.Model):
    """组会。组内公开；管理员建会、维护议程、纪要和行动项。"""

    group = models.ForeignKey("accounts.ResearchGroup", verbose_name="课题组", on_delete=models.PROTECT, related_name="meetings")
    date = models.DateField("日期")
    title = models.CharField("标题", max_length=100, default="组会")
    minutes = models.TextField("纪要", blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="创建人", on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = verbose_name_plural = "组会"
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.date} {self.title}"


class AgendaItem(models.Model):
    meeting = models.ForeignKey(Meeting, verbose_name="组会", on_delete=models.CASCADE, related_name="agenda")
    presenter = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="汇报人", on_delete=models.PROTECT, related_name="+")
    topic = models.CharField("汇报内容", max_length=200)
    order = models.PositiveSmallIntegerField("顺序", default=0)

    class Meta:
        verbose_name = verbose_name_plural = "议程"
        ordering = ["order", "id"]

    def __str__(self):
        return self.topic


class ActionItem(models.Model):
    """行动项。负责人或管理员标记完成（记 done_at）；新组会带入时转过去（carried_to），旧的这条算完成。"""

    meeting = models.ForeignKey(Meeting, verbose_name="组会", on_delete=models.CASCADE, related_name="actions")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="负责人", on_delete=models.PROTECT, related_name="action_items")
    content = models.CharField("事项", max_length=300)
    due_date = models.DateField("截止日期", null=True, blank=True)
    done_at = models.DateTimeField("完成时间", null=True, blank=True)
    # Brought into a later meeting's list (that copy carries on); this one counts as done and keeps the record.
    carried_to = models.ForeignKey(
        Meeting, verbose_name="转入组会", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    # On that copy: the item it came from, so removing the copy again opens the original instead of losing it.
    carried_from = models.ForeignKey(
        "self", verbose_name="带入自", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        verbose_name = verbose_name_plural = "行动项"
        ordering = ["id"]

    def __str__(self):
        return self.content


class MeetingFile(models.Model):
    meeting = models.ForeignKey(Meeting, verbose_name="组会", on_delete=models.CASCADE, related_name="files")
    file = models.FileField("文件", upload_to=meeting_file_upload_to, max_length=300)
    name = models.CharField("文件名", max_length=255)
    size = models.PositiveBigIntegerField("大小")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="上传人", on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = verbose_name_plural = "组会附件"
        ordering = ["created_at", "id"]

    def __str__(self):
        return self.name
