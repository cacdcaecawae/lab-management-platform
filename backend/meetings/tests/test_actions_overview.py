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
    carried = {"owner_id": student_a.pk, "content": "补实验", "due_date": "2026-11-20", "carried_from": open_item.pk}
    payload = {"date": "2026-11-16", "title": "组会", "minutes": "", "agenda": [], "actions": [carried]}
    client = api(manager)
    # an item that is not there to carry (another group's, or its meeting deleted) is refused, nothing saved
    stray = client.post("/api/meetings/", {**payload, "actions": [{**carried, "carried_from": foreign.pk}]}, format="json")
    assert stray.status_code == 409 and not Meeting.objects.filter(date=datetime.date(2026, 11, 16)).exists()
    foreign.refresh_from_db()
    assert foreign.done_at is None and foreign.carried_to_id is None

    # 学生甲 gets one carried row and one new row: told about the new one; 学生乙 about theirs
    fresh = [{"owner_id": student_a.pk, "content": "新任务", "due_date": None}, {"owner_id": student_b.pk, "content": "新事项", "due_date": None}]
    created = client.post("/api/meetings/", {**payload, "actions": [carried, *fresh]}, format="json")
    assert created.status_code == 201, created.data
    b = created.data["id"]
    open_item.refresh_from_db()
    assert open_item.done_at and open_item.carried_to_id == b
    assert [a["content"] for a in created.data["actions"]] == ["补实验", "新任务", "新事项"]
    notified = list(Notification.objects.filter(title="有新的组会行动项分配给你").values_list("recipient_id", flat=True))
    assert sorted(notified) == sorted([student_a.pk, student_b.pk])
    shown = api(student_a).get(f"/api/meetings/{last.pk}/").data["actions"][0]["carried_to"]
    assert shown == {"id": b, "date": "2026-11-16"}
    # a second new meeting carrying the same item (two organisers at once) is refused, not a second open copy
    again = client.post("/api/meetings/", {**payload, "date": "2026-11-17"}, format="json")
    assert again.status_code == 409 and again.data["code"] == "invalid_state" and "补实验" in again.data["message"]
    assert ActionItem.objects.filter(content="补实验", done_at__isnull=True).count() == 1
    # the carried one is ticked in the later meeting, not here
    assert api(student_a).post(f"/api/action-items/{open_item.pk}/done/", {"done": False}, format="json").status_code == 409

    # carried on again, B → C: B cannot be deleted while it holds an item carried on (it would come back twice)
    copy = ActionItem.objects.get(meeting_id=b, content="补实验")
    c = client.post("/api/meetings/", {**payload, "date": "2026-11-23", "actions": [{**carried, "carried_from": copy.pk}]}, format="json")
    assert c.status_code == 201, c.data
    refused = client.delete(f"/api/meetings/{b}/")
    assert refused.status_code == 409 and "2026-11-23" in refused.data["message"]
    assert ActionItem.objects.filter(content="补实验", done_at__isnull=True).count() == 1
    # from the newest back, each deletion opens the item before it again
    assert client.delete(f"/api/meetings/{c.data['id']}/").status_code == 204
    assert client.delete(f"/api/meetings/{b}/").status_code == 204
    open_item.refresh_from_db()
    assert open_item.done_at is None and open_item.carried_to_id is None
    # a form still holding the deleted meeting's copy cannot bring it back as a second one
    late = client.post("/api/meetings/", {**payload, "date": "2026-11-30", "actions": [{**carried, "carried_from": copy.pk}]}, format="json")
    assert late.status_code == 409 and "不在了" in late.data["message"]


def test_a_carried_row_removed_again_opens_its_original(api, group, manager, student_a):
    a = meeting(group, manager, 2)
    item = ActionItem.objects.create(meeting=a, owner=student_a, content="补实验")
    row = {"owner_id": student_a.pk, "content": "补实验", "carried_from": item.pk}
    base = {"title": "组会", "minutes": "", "agenda": []}
    client = api(manager)
    # one item twice in one save (two open copies), or an existing row claiming to be a copy: refused, nothing closed
    assert client.post("/api/meetings/", {**base, "date": "2026-11-09", "actions": [row, row]}, format="json").status_code == 400
    b = client.post("/api/meetings/", {**base, "date": "2026-11-09", "actions": [row]}, format="json").data["id"]
    copy = ActionItem.objects.get(meeting_id=b)
    assert copy.carried_from_id == item.pk
    other = ActionItem.objects.create(meeting=a, owner=student_a, content="交数据")
    bad = client.patch(f"/api/meetings/{b}/", {"actions": [{"id": copy.pk, "carried_from": other.pk}]}, format="json")
    assert bad.status_code == 400
    other.refresh_from_db()
    assert other.done_at is None
    # carried on again into C: B keeps that row, as B could not be deleted
    c = client.post("/api/meetings/", {**base, "date": "2026-11-16", "actions": [{**row, "carried_from": copy.pk}]}, format="json")
    kept = client.patch(f"/api/meetings/{b}/", {"actions": []}, format="json")
    assert kept.status_code == 409 and "2026-11-16" in kept.data["message"]
    # C drops its row (picked by mistake): B's is open again; then B drops it: the original is open again, never lost
    assert client.patch(f"/api/meetings/{c.data['id']}/", {"actions": []}, format="json").status_code == 200
    copy.refresh_from_db()
    assert copy.done_at is None and copy.carried_to_id is None
    assert client.patch(f"/api/meetings/{b}/", {"actions": []}, format="json").status_code == 200
    item.refresh_from_db()
    assert item.done_at is None and item.carried_to_id is None
    assert list(ActionItem.objects.filter(done_at__isnull=True).values_list("content", flat=True)) == ["补实验", "交数据"]
    assert api(student_a).post(f"/api/action-items/{item.pk}/done/", {"done": True}, format="json").status_code == 200


def test_an_old_meeting_cannot_take_items_of_a_later_one(api, group, manager, student_a):
    later = meeting(group, manager, 16)
    item = ActionItem.objects.create(meeting=later, owner=student_a, content="补实验")
    earlier = meeting(group, manager, 2)
    client = api(manager)
    # the page asks for the last meeting on or before the one being written
    assert [m["id"] for m in client.get("/api/meetings/", {"before": "2026-11-09"}).data["results"]] == [earlier.pk]
    assert client.get("/api/meetings/", {"before": "2026-13-45"}).status_code == 400
    row = {"owner_id": student_a.pk, "content": "补实验", "carried_from": item.pk}
    filled_in = client.post("/api/meetings/", {"date": "2026-11-09", "title": "补录", "agenda": [], "actions": [row]}, format="json")
    assert filled_in.status_code == 400 and "晚于这场组会" in str(filled_in.data)
    item.refresh_from_db()
    assert item.done_at is None and item.carried_to_id is None


def test_the_admin_does_not_delete_carried_items(group, manager, ops, student_a):
    from django.test import Client

    a, b, plain = meeting(group, manager, 2), meeting(group, manager, 9), meeting(group, manager, 16)
    item = ActionItem.objects.create(meeting=a, owner=student_a, content="补实验", done_at=timezone.now(), carried_to=b)
    ActionItem.objects.create(meeting=b, owner=student_a, content="补实验", carried_from=item)
    ActionItem.objects.create(meeting=plain, owner=student_a, content="交数据")
    client = Client()
    client.force_login(ops)
    for held in (a, b):  # the one carried out of, and the one carried into
        assert client.post(f"/admin/meetings/meeting/{held.pk}/delete/", {"post": "yes"}).status_code == 403
        page = client.get(f"/admin/meetings/meeting/{held.pk}/change/").content.decode()
        assert "actions-0-DELETE" not in page  # no row of its items can be ticked for deletion
    # the bulk "delete selected" refuses them too, and leaves a meeting without carried items deletable
    bulk = client.post("/admin/meetings/meeting/", {"action": "delete_selected", "_selected_action": [a.pk, b.pk], "post": "yes"})
    assert bulk.status_code == 403 and Meeting.objects.filter(pk__in=[a.pk, b.pk]).count() == 2
    assert "actions-0-DELETE" in client.get(f"/admin/meetings/meeting/{plain.pk}/change/").content.decode()
    assert client.post(f"/admin/meetings/meeting/{plain.pk}/delete/", {"post": "yes"}).status_code == 302


def test_dates_keep_a_carry_over_in_order(api, group, manager, student_a, ops):
    """A carry-over goes from an earlier meeting to a later one; editing a date (site or admin) cannot turn it round,
    and the admin cannot reopen an item whose copy carries on."""
    from django.test import Client

    a, b = meeting(group, manager, 9), meeting(group, manager, 16)
    item = ActionItem.objects.create(meeting=a, owner=student_a, content="补实验", done_at=timezone.now(), carried_to=b)
    copy = ActionItem.objects.create(meeting=b, owner=student_a, content="补实验", carried_from=item)
    client = api(manager)
    moved_back = client.patch(f"/api/meetings/{b.pk}/", {"date": "2026-11-02"}, format="json")
    assert moved_back.status_code == 400 and "2026-11-09" in str(moved_back.data)
    moved_on = client.patch(f"/api/meetings/{a.pk}/", {"date": "2026-11-20"}, format="json")
    assert moved_on.status_code == 400 and "2026-11-16" in str(moved_on.data)
    assert client.patch(f"/api/meetings/{b.pk}/", {"date": "2026-11-09"}, format="json").status_code == 200  # same day: fine

    admin = Client()
    admin.force_login(ops)
    form = {
        "date": "2026-11-09", "title": "组会", "minutes": "", "group": group.pk, "created_by": manager.pk,
        "agenda-TOTAL_FORMS": "0", "agenda-INITIAL_FORMS": "0",
        "files-TOTAL_FORMS": "0", "files-INITIAL_FORMS": "0",
        "actions-TOTAL_FORMS": "1", "actions-INITIAL_FORMS": "1",
        "actions-0-id": item.pk, "actions-0-meeting": a.pk, "actions-0-owner": student_a.pk, "actions-0-content": "补实验",
        "actions-0-due_date": "", "actions-0-done_at_0": "", "actions-0-done_at_1": "",
    }
    reopened = admin.post(f"/admin/meetings/meeting/{a.pk}/change/", form)
    assert reopened.status_code == 200 and "完成状态在那边改" in reopened.content.decode()  # the form again, with the error
    item.refresh_from_db()
    assert item.done_at is not None
    assert ActionItem.objects.filter(done_at__isnull=True).count() == 1  # only the copy is open
    form_b = {**form, "date": "2026-11-02", "actions-TOTAL_FORMS": "0", "actions-INITIAL_FORMS": "0"}
    for key in [k for k in form_b if k.startswith("actions-0-")]:
        del form_b[key]
    later_first = admin.post(f"/admin/meetings/meeting/{b.pk}/change/", form_b)
    assert later_first.status_code == 200 and "日期不能早于那天" in later_first.content.decode()
    b.refresh_from_db()
    assert b.date.isoformat() == "2026-11-09" and copy.carried_from_id == item.pk
