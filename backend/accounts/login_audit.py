"""Best-effort, redacted login telemetry; never read or store a password or raw form field."""
import logging
from ipaddress import ip_address
from threading import Lock

from django.conf import settings
from django.core.cache import cache
from django.db import DatabaseError, transaction
from django.utils import timezone
from rest_framework.settings import api_settings

from .models import LoginEvent, User

logger = logging.getLogger(__name__)
_minute_lock = Lock()
_last_attempt = None


def parse_ip(value):
    try:
        # Scope-qualified addresses cannot be stored as PostgreSQL inet.
        return str(ip_address(value)) if value and "%" not in value else None
    except ValueError:
        return None


def source_address(request):
    """Use only the configured suffix of the trusted proxy chain, otherwise the socket peer.

    Production keeps Django private behind the documented ingress topology.
    """
    proxies = api_settings.NUM_PROXIES
    chain = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")
    forwarded = parse_ip(chain[-proxies].strip()) if proxies and 0 < proxies <= len(chain) else None
    return forwarded or parse_ip(request.META.get("REMOTE_ADDR", ""))


def record_attempt(request, *, user=None, candidate=None):
    if not settings.LOGIN_AUDIT_ENABLED:
        return
    try:
        with transaction.atomic():
            account_id = user.pk if user is not None else None
            # Link failures to an existing account without persisting arbitrary form data.
            if user is None and isinstance(candidate, str) and len(candidate) <= 150 and "\x00" not in candidate:
                account_id = User.objects.filter(username=candidate).values_list("pk", flat=True).first()
            LoginEvent.objects.create(
                user_id=account_id, ip=source_address(request), at=timezone.now(),
                outcome=LoginEvent.Outcome.SUCCESS if user is not None else LoginEvent.Outcome.FAILED,
            )
    except DatabaseError:
        # Do not attach diagnostic SQL or exception strings that may contain identifiers.
        logger.warning("Login audit event could not be written")


def record_throttle_minute():
    global _last_attempt
    if not settings.LOGIN_AUDIT_ENABLED:
        return
    minute = timezone.now().replace(second=0, microsecond=0)
    # Once per worker per minute, independent of username, address, or request count.
    with _minute_lock:
        if _last_attempt == minute:
            return
        _last_attempt = minute
    try:
        # A bounded shared marker avoids audit inserts on each worker/request; the DB
        # constraint is the final deduplication even if the cache evicts a marker.
        if cache.add(f"login-audit-throttle:{minute.timestamp():.0f}", True, timeout=120):
            with transaction.atomic():
                LoginEvent.objects.get_or_create(at=minute, outcome=LoginEvent.Outcome.THROTTLED)
    except Exception:
        # Cache implementations may raise different connection errors. This path
        # must never change the existing DRF response or log captured data.
        logger.warning("Login throttle audit minute could not be written")
