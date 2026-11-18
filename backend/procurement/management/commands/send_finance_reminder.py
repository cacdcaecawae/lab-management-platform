import logging

from django.core.management.base import BaseCommand

from accounts.models import ResearchGroup
from core import mail
from procurement.mail import send_finance_reminder

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "给各课题组的财务邮箱发一封提醒，列出已交财务、尚未到账的报销。由宿主机定时任务每周一 9:00 运行。"

    def handle(self, **options):
        if not mail.enabled():
            self.stdout.write("平台没有启用邮件（系统管理 → 邮件），不发送")
            return
        for group in ResearchGroup.objects.exclude(finance_email="").order_by("id"):
            try:  # one group's failure must not stop the others
                sent = send_finance_reminder(group)
            except Exception:
                logger.exception("财务提醒发送失败：%s", group.name)
                continue
            self.stdout.write(f"{group.name}：{sent} 笔" if sent else f"{group.name}：没有待到账的报销，不发送")
