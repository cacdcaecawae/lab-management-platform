"""Issue #48 N4: action items across meetings, advisors running meetings, carrying open items into a new meeting."""
import datetime

import pytest
from django.utils import timezone

from core.models import Notification
from meetings.models import ActionItem, Meeting

pytestmark = pytest.mark.django_db


def meeting(group, manager, day, **extra):
    return Meeting.objects.create(group=group, date=datetime.date(2026, 11, day), created_by=manager, **extra)


def test_overview_lists_the_group_open_items_most_urgent_first(api, group, other_group, student_a, student_b, manager, other_manager):
    old, new = meeting(group, manager, 2), meeting(group, manager, 9)
    later = ActionItem.objects.create(meeting=new, owner=student_a, content="补实验", due_date=datetime.date(2026, 12, 1))
    soon = ActionItem.objects.create(meeting=old, owner=student_b, content="交数据", due_date=datetime.date(2026, 11, 3))
    ActionItem.objects.create(meeting=old, owner=student_a, content="没有截止")
    ActionItem.objects.create(meeting=old, owner=student_a, content="做完了", done_at=timezone.now())
    ActionItem.objects.create(meeting=meeting(other_group, other_manager, 9), owner=other_manager, content="外组")
    client = api(student_a)
    rows = client.get("/api/action-items/", {"open": "1"}).data["results"]
    assert [r["content"] for r in rows] == ["交数据", "补实验", "没有截止"]
    assert rows[0]["meeting"] == {"id": old.pk, "date": "2026-11-02", "title": "组会"}
    assert [r["content"] for r in client.get("/api/action-items/", {"owner": student_a.pk, "open": "1"}).data["results"]] == ["补实验", "没有截止"]
    assert [r["content"] for r in client.get("/api/action-items/", {"open": "0"}).data["results"]] == ["做完了"]
    assert client.get("/api/action-items/", {"owner": "x"}).data["count"] == 0
    # ticking from the overview uses the same rule as the meeting page: the owner or a manager
    assert client.post(f"/api/action-items/{soon.pk}/done/", {"done": True}).status_code == 403
    assert client.post(f"/api/action-items/{later.pk}/done/", {"done": True}).status_code == 200
    assert api(other_manager).post(f"/api/action-items/{later.pk}/done/", {"done": False}).status_code == 404


def test_advisors_create_and_edit_meetings_but_only_managers_delete(api, group, student_a, manager, advisor):
    payload = {"date": "2026-11-16", "title": "组会", "minutes": "", "agenda": [], "actions": []}
    assert api(student_a).post("/api/meetings/", payload, format="json").status_code == 403
    created = api(advisor).post("/api/meetings/", payload, format="json")
    assert created.status_code == 201
    pk = created.data["id"]
    assert api(advisor).patch(f"/api/meetings/{pk}/", {"title": "导师主持"}, format="json").status_code == 200
    assert api(advisor).delete(f"/api/meetings/{pk}/").status_code == 403
    assert api(manager).delete(f"/api/meetings/{pk}/").status_code == 204


def test_carried_items_close_the_old_ones_and_are_not_new_assignments(api, group, other_group, student_a, student_b, manager, other_manager):
    last = meeting(group, manager, 9)
    open_item = ActionItem.objects.create(meeting=last, owner=student_a, content="补实验", due_date=datetime.date(2026, 11, 20))
    foreign = ActionItem.objects.create(meeting=meeting(other_group, other_manager, 9), owner=other_manager, content="外组")
    payload = {
        "date": "2026-11-16", "title": "组会", "minutes": "", "agenda": [],
        "actions": [
            {"owner_id": student_a.pk, "content": "补实验", "due_date": "2026-11-20", "carried_from": open_item.pk},
            {"owner_id": student_b.pk, "content": "新事项", "due_date": None, "carried_from": foreign.pk},
        ],
    }
    created = api(manager).post("/api/meetings/", payload, format="json")
    assert created.status_code == 201, created.data
    open_item.refresh_from_db()
    foreign.refresh_from_db()
    assert open_item.done_at and open_item.carried_to_id == created.data["id"]
    assert foreign.done_at is None and foreign.carried_to_id is None  # another group's item is left alone
    assert [a["content"] for a in created.data["actions"]] == ["补实验", "新事项"]
    notified = set(Notification.objects.filter(title="有新的组会行动项分配给你").values_list("recipient_id", flat=True))
    assert notified == {student_b.pk}
    shown = api(student_a).get(f"/api/meetings/{last.pk}/").data["actions"][0]["carried_to"]
    assert shown == {"id": created.data["id"], "date": "2026-11-16"}
