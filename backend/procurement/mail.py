"""Procurement mail. Optional like all mail here (core.mail): while mail is off nothing is sent. Notifications run
after the commit and a failure is only logged; it never undoes the submission or approval that triggered it."""

from django.utils import timezone

from accounts.models import User
from core import mail

from .models import PurchaseRequest, Reimbursement

S = PurchaseRequest.Status


def mail_users(users, subject, body):
    recipients = sorted({u.email for u in users if u.is_active and u.email})
    mail.send_quietly(subject, body, recipients, "采购通知")


def notify(purchase_id, comment=""):
    """Tell whoever acts next, by the state the purchase is in now: reviewers when it waits for a review,
    the applicant when it was sent back (status draft, with `comment`), approved or arrived."""
    purchase = PurchaseRequest.objects.select_related("owner").prefetch_related("items").get(pk=purchase_id)
    owner = purchase.owner
    head = f"{purchase.code} {owner.display_name}：{purchase.purpose[:40]}（合计 {purchase.total} 元）"
    role = {S.PENDING_INITIAL: User.Role.MANAGER, S.PENDING_FINAL: User.Role.ADVISOR}.get(purchase.status)
    if role:
        reviewers = User.objects.filter(group_id=owner.group_id, role=role).exclude(pk=owner.pk)
        stage = "初审" if role == User.Role.MANAGER else "终审"
        mail_users(reviewers, f"[采购待{stage}] {purchase.code}", f"{head}\n\n请登录 Phase，在“我的审批”中处理。")
        return
    subject, body = {
        S.DRAFT: ("退回修改", f"审批意见：{comment}\n\n请修改后重新提交。"),
        S.APPROVED: ("已批准", "可以开始采购。"),
        S.ARRIVED: ("已到货", "管理员已登记到货。"),
    }.get(purchase.status, (None, None))
    if subject:
        mail_users([owner], f"[采购{subject}] {purchase.code}", f"{head}\n\n{body}")


def finance_reminder(group):
    """(count, subject, body) listing the group's reimbursements handed to finance and not yet paid."""
    pending = (
        Reimbursement.objects.filter(owner__group=group, status=Reimbursement.Status.SUBMITTED)
        .select_related("owner", "fund")
        .order_by("submitted_at", "id")
    )
    lines = [
        f"{r.code}  {r.owner.display_name}  {r.fund.code}  {r.get_category_display()}  {r.amount} 元  "
        f"交财务 {timezone.localtime(r.submitted_at):%Y-%m-%d}  {r.description}"
        for r in pending
    ]
    total = sum(r.amount for r in pending)
    body = f"以下 {len(lines)} 笔报销已交财务、尚未到账，合计 {total} 元：\n\n" + "\n".join(lines)
    return len(lines), f"[报销提醒] {group.name}：{len(lines)} 笔待到账", body


def send_finance_reminder(group):
    """Mail the reminder to group.finance_email. Returns how many reimbursements it listed (0: nothing sent).
    Raises on SMTP errors: the caller decides whether that is fatal."""
    count, subject, body = finance_reminder(group)
    if not (count and group.finance_email):
        return 0
    return count if mail.send(subject, body, [group.finance_email]) else 0
