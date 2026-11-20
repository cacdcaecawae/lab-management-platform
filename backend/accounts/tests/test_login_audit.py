from datetime import datetime, timedelta, timezone
from io import StringIO
from unittest.mock import Mock

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.db import DatabaseError
from rest_framework.settings import api_settings
from rest_framework.test import APIClient, APIRequestFactory

from accounts import login_audit
from accounts.models import LoginEvent, User
from conftest import PASSWORD

pytestmark = pytest.mark.django_db
LOGIN = "/api/auth/login/"
EVENTS = "/api/system/logins/"


@pytest.fixture(autouse=True)
def enable_login_audit(settings):
    settings.LOGIN_AUDIT_ENABLED = True


def test_auth_records_validated_outcomes_only(student_a, monkeypatch):
    cache.clear()
    client = APIClient()
    client.post(LOGIN, {"username": student_a.username, "password": "wrong"}, HTTP_X_FORWARDED_FOR="203.0.113.5")
    client.post(LOGIN, {"username": "synthetic value not a known account", "password": "not-an-audit-field"})
    assert client.post(LOGIN, {"username": student_a.username, "password": PASSWORD}).status_code == 200
    events = list(LoginEvent.objects.order_by("pk").values("user_id", "outcome", "ip"))
    assert [(e["user_id"], e["outcome"]) for e in events] == [
        (student_a.pk, "failed"), (None, "failed"), (student_a.pk, "success"),
    ]
    assert events[0]["ip"] == "203.0.113.5"
    assert {f.name for f in LoginEvent._meta.fields} == {"id", "user", "outcome", "at", "ip"}
    client.logout()
    writer = Mock(side_effect=DatabaseError("synthetic"))
    monkeypatch.setattr(LoginEvent.objects, "create", writer)
    assert client.post(LOGIN, {"username": student_a.username, "password": PASSWORD}).status_code == 200
    writer.assert_called_once()


def test_respects_deployment_proxy_count(monkeypatch):
    factory = APIRequestFactory()
    req = factory.get("/", REMOTE_ADDR="192.0.2.10", HTTP_X_FORWARDED_FOR="2001:db8::1, 192.0.2.20")
    monkeypatch.setattr(api_settings, "NUM_PROXIES", 1)
    assert login_audit.source_address(req) == "192.0.2.20"
    monkeypatch.setattr(api_settings, "NUM_PROXIES", 2)
    assert login_audit.source_address(req) == "2001:db8::1"
    for count in (0, None, 3):
        monkeypatch.setattr(api_settings, "NUM_PROXIES", count)
        assert login_audit.source_address(req) == "192.0.2.10"
    malformed = factory.get("/", REMOTE_ADDR="192.0.2.10", HTTP_X_FORWARDED_FOR="not-an-ip")
    monkeypatch.setattr(api_settings, "NUM_PROXIES", 1)
    assert login_audit.source_address(malformed) == "192.0.2.10"


def test_throttles_roll_up_instead_of_writing_every_response(student_a, monkeypatch):
    cache.clear()
    monkeypatch.setattr(login_audit, "_last_attempt", None)
    monkeypatch.setattr(login_audit.timezone, "now", lambda: datetime(2026, 11, 19, 5, 4, 32, tzinfo=timezone.utc))
    add = Mock(wraps=cache.add)
    monkeypatch.setattr(login_audit.cache, "add", add)
    client = APIClient()
    payload = {"username": student_a.username, "password": "wrong"}
    for _ in range(5):
        assert client.post(LOGIN, payload).status_code != 429
    for _ in range(8):
        assert client.post(LOGIN, payload).status_code == 429
    assert add.call_count == 1
    assert LoginEvent.objects.filter(outcome="failed").count() == 5
    event = LoginEvent.objects.get(outcome="throttled")
    assert event.at.second == 0 and event.user_id is None and event.ip is None
    # Simulate another worker or a restart: shared marker survives; even without it, DB uniqueness deduplicates.
    monkeypatch.setattr(login_audit, "_last_attempt", None)
    assert client.post(LOGIN, payload).status_code == 429
    cache.delete(f"login-audit-throttle:{event.at.timestamp():.0f}")
    monkeypatch.setattr(login_audit, "_last_attempt", None)
    assert client.post(LOGIN, payload).status_code == 429
    assert LoginEvent.objects.filter(outcome="throttled").count() == 1


def test_ops_filter_pagination_recent_summary_and_purge(api, student_a, student_b, manager, monkeypatch):
    ops = User.objects.create(username="ops-audit", is_superuser=True, must_change_password=False)
    now = datetime(2026, 11, 19, 5, tzinfo=timezone.utc)
    monkeypatch.setattr(login_audit.timezone, "now", lambda: now)
    for outcome, who, age in [
        ("success", student_a, 1), ("failed", student_a, 2), ("failed", student_a, 3),
        ("failed", student_b, 4), ("failed", None, 5), ("throttled", None, 6),
        ("failed", student_b, 24 * 181), ("failed", student_b, 24 * 180),
    ]:
        LoginEvent.objects.create(user=who, outcome=outcome, at=now - timedelta(hours=age))
    assert api(manager).get(EVENTS).status_code == 403
    client = api(ops)
    page = client.get(EVENTS, {"username": student_a.username, "outcome": "failed", "page_size": 1}).data
    assert page["count"] == 2 and page["next"]
    assert page["results"][0]["account"] == {"id": student_a.pk, "username": student_a.username}
    assert page["top_failed_24h"] == [
        {"user_id": student_a.pk, "user__username": student_a.username, "failures": 2},
        {"user_id": student_b.pk, "user__username": student_b.username, "failures": 1},
    ]
    assert client.get(EVENTS).data["count"] == 7
    assert client.get(EVENTS, {"from": now.isoformat(), "to": now.isoformat()}).status_code == 400
    assert client.get(EVENTS, {"outcome": "unknown"}).status_code == 400
    assert client.get(EVENTS, {"to": (now - timedelta(hours=3)).isoformat()}).data["count"] == 4
    output = StringIO()
    call_command("purge_login_events", "--dry-run", stdout=output)
    assert "Expired login events: 1" in output.getvalue() and LoginEvent.objects.count() == 8
    call_command("purge_login_events", stdout=output)
    call_command("purge_login_events", stdout=output)
    assert LoginEvent.objects.count() == 7 and "Deleted login events: 0" in output.getvalue()


def test_disabled_audit_keeps_authentication_but_stores_nothing(api, student_a, settings):
    settings.LOGIN_AUDIT_ENABLED = False
    cache.clear()
    client = APIClient()
    assert client.post(LOGIN, {"username": student_a.username, "password": "wrong"}).status_code == 403
    assert client.post(LOGIN, {"username": student_a.username, "password": PASSWORD}).status_code == 200
    login_audit.record_throttle_minute()
    assert LoginEvent.objects.count() == 0
    ops = User.objects.create(username="ops-disabled", is_superuser=True, must_change_password=False)
    assert api(ops).get(EVENTS).data["audit_enabled"] is False
