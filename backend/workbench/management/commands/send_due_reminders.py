"""Send a single daily digest per eligible account, with a durable pre-send claim."""

import os
import smtplib
from datetime import date, timedelta
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand, CommandError
from django.db.models import F
from django.utils import timezone

from accounts.models import User
from core import mail
from workbench.models import ReminderDelivery
from workbench.reminders import build_digests


State = ReminderDelivery.State
MAX_ATTEMPTS = 3
SHANGHAI = ZoneInfo("Asia/Shanghai")


def site_origin():
    setting = os.environ.get("SITE_URL", "").strip()
    if not setting:
        return ""
    try:
        url = urlsplit(setting)
        if (
            url.scheme not in ("https", "http") or not url.hostname or url.username or url.password
            or url.query or url.fragment or url.path not in ("", "/")
            or chr(92) in setting or any(c.isspace() for c in setting)
        ):
            raise ValueError
    except ValueError:
        raise CommandError("SITE_URL 必须是站点 HTTP(S) 地址（不含账号、路径、查询或片段）") from None
    return setting.rstrip("/")


def claim(recipient, day):
    """Acquire authorization to send once; the unique key plus update condition arbitrate parallel invocations."""
    row, created = ReminderDelivery.objects.get_or_create(recipient=recipient, day=day)
    if created:
        return row
    acquired = ReminderDelivery.objects.filter(
        pk=row.pk, state=State.RETRYABLE, attempts__lt=MAX_ATTEMPTS,
    ).update(state=State.SENDING, attempts=F("attempts") + 1, updated_at=timezone.now())
    if not acquired:
        return None
    row.refresh_from_db(fields=["attempts"])
    return row


def failure_state(exc):
    # Whitelist definitive refusals. A disconnect/timeout could happen *after* SMTP accepts DATA.
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        codes = [result[0] for result in exc.recipients.values()]
    elif isinstance(exc, (smtplib.SMTPAuthenticationError, smtplib.SMTPSenderRefused, smtplib.SMTPDataError)):
        codes = [exc.smtp_code]
    else:
        return State.UNCERTAIN
    if codes and all(400 <= code < 500 for code in codes):
        return State.RETRYABLE
    if codes and all(400 <= code < 600 for code in codes):
        return State.FAILED
    return State.UNCERTAIN


class Command(BaseCommand):
    help = "按上海时区合并并发送试件、校准、行动项和周报提醒；--dry-run 不发送也不改账本。"

    def add_arguments(self, parser):
        parser.add_argument("--date", metavar="YYYY-MM-DD")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *, date=None, dry_run=False, **options):
        business_today = timezone.localdate(timezone=SHANGHAI)
        today = self.parse_day(date) if date is not None else business_today
        if today > business_today and not dry_run:
            raise CommandError("未来业务日期只能使用 --dry-run 预览，不能发送提醒。")
        enabled = mail.enabled()
        if not enabled and not dry_run:
            self.stdout.write("邮件未启用，跳过。")
            return
        origin = site_origin()
        self.stdout.write(f"提醒日期：{today}（Asia/Shanghai）")
        if dry_run and not enabled:
            self.stdout.write("邮件未启用，以下仅预览。")
        outcomes = {state: 0 for state in State.values}
        outcomes["skipped"] = 0
        for recipient, count, body in build_digests(today, origin):
            subject = f"[课题组管理平台] 今日提醒（{count} 项）"
            if dry_run:
                state = ReminderDelivery.objects.filter(recipient=recipient, day=today).values_list("state", flat=True).first()
                self.stdout.write(f"预览：账号 ID {recipient.pk}（{state or '未认领'}）\n{subject}\n{body}")
                continue
            # Re-read authorization just before claiming; do not send a snapshot from an old group.
            address = User.objects.filter(
                pk=recipient.pk, is_active=True, group_id=recipient.group_id, role=recipient.role, email=recipient.email,
            ).values_list("email", flat=True).first()
            if not address:
                outcomes["skipped"] += 1
                continue
            row = claim(recipient, today)
            if row is None:
                state = ReminderDelivery.objects.values_list("state", flat=True).get(recipient=recipient, day=today)
                outcomes["skipped" if state == State.SENT else state] += 1
                continue
            try:
                state = State.SENT if mail.send(subject, body, [address.strip()]) else State.RETRYABLE
            except Exception as exc:  # transport errors for one user do not stop the others
                state = failure_state(exc)
            if state == State.RETRYABLE and row.attempts >= MAX_ATTEMPTS:
                state = State.FAILED
            ReminderDelivery.objects.filter(pk=row.pk).update(state=state, updated_at=timezone.now())
            outcomes[state] += 1
        if dry_run:
            return
        self.stdout.write("，".join(f"{state}={count}" for state, count in outcomes.items()))
        if any(outcomes[state] for state in (State.SENDING, State.RETRYABLE, State.FAILED, State.UNCERTAIN)):
            raise CommandError("有提醒未确认发送；仅明确的临时拒绝可在同日重试，其他记录不会自动重发。")

    @staticmethod
    def parse_day(value):
        try:
            day = date.fromisoformat(value)
            if day.isoformat() != value or not date.min + timedelta(days=7) <= day <= date.max - timedelta(days=30):
                raise ValueError
            return day
        except (TypeError, ValueError):
            raise CommandError("--date 必须为 YYYY-MM-DD") from None
