import re

from django.contrib.auth import get_user_model

from .models import Notification


LOCAL_PATH = re.compile(r"/[a-z][a-z0-9-]*(?:/[0-9]+)?")


def notify(group_id, title, link, *, recipient_ids=None, role="", exclude_ids=(), body=""):
    """Write inside the caller's transaction, with group and role checked even for explicit IDs."""
    if not LOCAL_PATH.fullmatch(link):
        raise ValueError("Notification link must be a local application path")
    if not group_id:
        return
    recipients = get_user_model().objects.filter(group_id=group_id, is_active=True)
    if role:
        recipients = recipients.filter(role=role)
    if recipient_ids is not None:
        recipients = recipients.filter(pk__in=recipient_ids)
    else:
        if not role:  # accidental site-wide/all-group broadcast is not an event primitive
            raise ValueError("Notification recipients require explicit IDs or a scoped role")
    recipients = recipients.exclude(pk__in=exclude_ids).values_list("pk", flat=True)
    Notification.objects.bulk_create([
        Notification(
            recipient_id=pk, group_id=group_id, audience_role=role, title=title, body=body, link=link,
        )
        for pk in recipients
    ])
