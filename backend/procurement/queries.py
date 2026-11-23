"""Purchase queries shared by the purchase list and the workbench: one definition of "waits for my review"."""

from django.db.models import BooleanField, Exists, ExpressionWrapper, OuterRef, Q


from .models import Approval, PurchaseRequest

S = PurchaseRequest.Status


def returned_flag():
    """True for a draft whose latest submission was sent back (a withdrawal is not a return)."""
    sent_back = Approval.objects.filter(
        request=OuterRef("pk"), verdict=Approval.Verdict.RETURN, created_at__gte=OuterRef("submitted_at")
    )
    return ExpressionWrapper(Q(status=S.DRAFT) & Exists(sent_back), output_field=BooleanField())


def awaiting_review(purchases, user):
    """The part of an (already scoped) queryset that waits for `user`'s review: initial ones for a manager, final ones
    for an approver (both for someone with both tags)."""
    statuses = [*([S.PENDING_INITIAL] if user.is_manager else []), *([S.PENDING_FINAL] if user.is_approver else [])]
    return purchases.filter(status__in=statuses).exclude(owner=user)
