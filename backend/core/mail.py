"""All outgoing mail goes through here. The SMTP account is set by the ops account in 系统管理 → 邮件 (SiteSettings);
while mail is off nothing is sent and alerts only show on the workbench."""

import logging
import smtplib
import socket
import ssl

from django.core import mail as django_mail
from django.utils import timezone

from .models import SiteSettings

logger = logging.getLogger(__name__)
TIMEOUT = 10  # seconds; a test mail waits this long at most for an unreachable server


def _config():
    # Read only: the row is created when the ops account opens 系统管理, so its history starts with the ops account,
    # not with whichever request first asked whether mail is on. No row yet means mail is off.
    return SiteSettings.objects.filter(pk=1).first()


def enabled():
    config = _config()
    return bool(config and config.mail_enabled)


def describe(exc):
    """The server's reason plus what to check, e.g. "535 Error: authentication failed。账号或授权码不对……"."""
    if isinstance(exc, smtplib.SMTPRecipientsRefused):  # one (code, reason) per refused address
        reason = "；".join(f"{to}: {code} {_text(text)}" for to, (code, text) in exc.recipients.items())
    elif isinstance(exc, smtplib.SMTPResponseException):
        reason = f"{exc.smtp_code} {_text(exc.smtp_error)}"
    else:
        reason = str(exc) or type(exc).__name__
    advice = hint(exc)
    return f"{reason[:400]}。{advice}" if advice else reason[:500]


def _text(value):
    return value.decode(errors="replace") if isinstance(value, bytes) else str(value)


def hint(exc):
    """What to check for the failures a school mailbox usually gives while it is being set up."""
    code = getattr(exc, "smtp_code", None)
    if isinstance(exc, smtplib.SMTPAuthenticationError) or code in (534, 535):
        return "账号或授权码不对。学校邮箱一般要先在网页邮箱的设置里开启 SMTP 服务、生成客户端授权码，这里填授权码，不是登录密码"
    if code == 530:  # e.g. "Must issue a STARTTLS command first", "Authentication required"
        return "服务器要求先加密或先登录。把加密方式改为 SSL 或 STARTTLS，并填写账号和授权码"
    if isinstance(exc, smtplib.SMTPSenderRefused):
        return "服务器不接受这个发件人。发件人地址一般必须和账号相同，可以把发件人留空"
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return "收件地址被拒。检查地址有没有写错；有的学校邮箱不允许发往校外"
    if isinstance(exc, smtplib.SMTPDataError):
        return "服务器拒收了这封邮件，常见原因是被判为垃圾邮件或超出发信频率。换一个收件地址再试，或者问学校网络中心"
    if isinstance(exc, smtplib.SMTPNotSupportedError):
        if "AUTH" in str(exc):  # login() where the server offers no login, often only before encryption
            return "服务器在这里不提供登录，多数邮箱要先加密才允许登录。把加密方式改为 SSL 或 STARTTLS；服务器确实不需要登录时，把账号留空"
        return "这个端口不支持 STARTTLS。改用 SSL（一般是 465 端口）"
    if isinstance(exc, ssl.SSLCertVerificationError):
        if getattr(exc, "verify_code", None) in (62, 64):  # X509_V_ERR_HOSTNAME_MISMATCH, _IP_ADDRESS_MISMATCH
            return "证书上的域名和填写的服务器地址不一致。SMTP 服务器要填证书上的域名（例如 smtp.xxx.edu.cn），不要填 IP 地址或别名"
        return "服务器证书不受信任（自签名，或证书链不完整）。先确认填的是学校公布的 SMTP 地址；地址没错的话，要请学校网络中心处理"
    if isinstance(exc, (ssl.SSLError, smtplib.SMTPServerDisconnected)):
        return "加密方式和端口对不上。465 端口选 SSL，587 端口选 STARTTLS"
    if isinstance(exc, socket.gaierror):
        return "找不到这个服务器。检查 SMTP 服务器地址有没有拼错，以及这台机器能不能访问外网"
    if isinstance(exc, ConnectionRefusedError):
        return "服务器拒绝连接。检查端口"
    if isinstance(exc, TimeoutError):  # socket.timeout is TimeoutError
        return "连接超时。检查服务器地址、端口和加密方式（465 选 SSL）；云服务器通常封了 25 端口，改用 465"
    return ""


def send(subject, body, recipients, *, test=False):
    """Send one message; False (nothing sent) while mail is off or there is no recipient. A test mail is sent even
    while mail is off, so the account can be tried before switching it on. SMTP errors are recorded as the last
    failure (shown in 系统管理) and raised."""
    config = _config()
    recipients = list(recipients)
    if not recipients or config is None or not (config.mail_enabled or test):
        return False
    connection = django_mail.get_connection(
        host=config.mail_host,
        port=config.mail_port,
        username=config.mail_username,
        password=config.mail_password,
        use_ssl=config.mail_security == SiteSettings.Security.SSL,
        use_tls=config.mail_security == SiteSettings.Security.STARTTLS,
        timeout=TIMEOUT,
    )
    try:
        django_mail.send_mail(subject, body, config.sender, recipients, connection=connection)
    except Exception as exc:
        # update(), not save(): a failure is not a settings change and must not show in the settings history
        SiteSettings.objects.filter(pk=config.pk).update(last_mail_error=describe(exc), last_mail_error_at=timezone.now())
        raise
    if config.last_mail_error:
        SiteSettings.objects.filter(pk=config.pk).update(last_mail_error="", last_mail_error_at=None)
    return True


def send_quietly(subject, body, recipients, what):
    """For notifications after a commit: a failure is logged and recorded, never raised, so it cannot undo the
    change that triggered it."""
    try:
        return send(subject, body, recipients)
    except Exception:  # SMTP, DNS, timeouts: any of them must not turn a saved change into a 500
        logger.exception("%s邮件发送失败：%s", what, subject)
        return False
