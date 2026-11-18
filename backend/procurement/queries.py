"""Purchase queries shared by the purchase list and the workbench: one definition of "waits for my review"."""

from django.db.models import BooleanField, Exists, ExpressionWrapper, OuterRef, Q

from accounts.models import User

from .models import Approval, PurchaseRequest

S = PurchaseRequest.Status


def returned_flag():
    """True for a draft whose latest submission was sent back (a withdrawal is not a return)."""
    sent_back = Approval.objects.filter(
        request=OuterRef("pk"), verdict=Approval.Verdict.RETURN, created_at__gte=OuterRef("submitted_at")
    )
    return ExpressionWrapper(Q(status=S.DRAFT) & Exists(sent_back), output_field=BooleanField())


def awaiting_review(purchases, user):
    """The part of an (already scoped) queryset that waits for `user`'s review."""
    stage_status = {User.Role.MANAGER: S.PENDING_INITIAL, User.Role.ADVISOR: S.PENDING_FINAL}.get(user.role)
    if not stage_status:
        return purchases.none()
    return purchases.filter(status=stage_status).exclude(owner=user)
