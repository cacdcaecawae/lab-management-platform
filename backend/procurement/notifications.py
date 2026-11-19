from accounts.models import User
from core.notifications import notify

from .models import PurchaseRequest


S = PurchaseRequest.Status


def notify_purchase(purchase):
    """Capture the transition inside the same transaction; don't re-read a potentially newer state."""
    group_id = purchase.owner.group_id
    path = f"/purchases/{purchase.pk}"
    reviewer = {
        S.PENDING_INITIAL: (User.Role.MANAGER, "采购申请待初审"),
        S.PENDING_FINAL: (User.Role.ADVISOR, "采购申请待终审"),
    }.get(purchase.status)
    if reviewer:
        role, title = reviewer
        notify(group_id, title, path, role=role, exclude_ids=[purchase.owner_id])
        return
    title = {
        S.DRAFT: "采购申请退回修改",
        S.APPROVED: "采购申请已批准",
        S.ARRIVED: "采购申请已到货",
    }.get(purchase.status)
    if title:
        notify(group_id, title, path, recipient_ids=[purchase.owner_id])
