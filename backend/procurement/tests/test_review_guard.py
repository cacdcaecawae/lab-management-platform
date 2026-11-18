"""Fast guard checks; PostgreSQL/API regressions live in test_procurement.py."""
from contextlib import nullcontext
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from rest_framework.exceptions import ValidationError

from core.exceptions import Conflict
from procurement.models import Approval
from procurement.views import PurchaseViewSet


@pytest.mark.parametrize("verdict", ["approve", "return"])
@pytest.mark.parametrize("submitted_seen", ["old", "one_microsecond_old", "current", "missing", None, "malformed"])
def test_review_submission_guard_without_database(monkeypatch, verdict, submitted_seen):
    current = datetime(2026, 11, 18, 2, microsecond=123456, tzinfo=timezone.utc)
    purchase = SimpleNamespace(
        pk=1, owner_id=2, owner=SimpleNamespace(role="student"), status="pending_initial",
        total=Decimal("2536.50"), submitted_at=current, save=Mock(),
    )
    view = PurchaseViewSet()
    view.lock = Mock(return_value=purchase)
    view.respond = lambda pk: purchase.status
    body = {"verdict": verdict, "comment": "审批意见", "status_seen": "pending_initial", "total_seen": "2536.50"}
    if submitted_seen != "missing":
        body["submitted_seen"] = {
            "old": "2026-11-18T01:00:00Z", "current": "2026-11-18T10:00:00.123456+08:00",
            "one_microsecond_old": "2026-11-18T02:00:00.123455Z",
            None: None, "malformed": "not-a-date",
        }[submitted_seen]
    request = SimpleNamespace(user=SimpleNamespace(id=1, is_supervisor=True, role="manager"), data=body)
    create = Mock()
    monkeypatch.setattr("procurement.views.transaction.atomic", lambda: nullcontext())
    monkeypatch.setattr("procurement.views.transaction.on_commit", Mock())
    monkeypatch.setattr(Approval.objects, "create", create)
    if submitted_seen == "current":
        assert view.review(request) == ("pending_final" if verdict == "approve" else "draft")
        create.assert_called_once()
        purchase.save.assert_called_once()
    else:
        with pytest.raises(Conflict if submitted_seen in ("old", "one_microsecond_old") else ValidationError):
            view.review(request)
        create.assert_not_called()
        purchase.save.assert_not_called()
