"""A parent's PATCH must not make newly inserted nested records incomplete."""
from datetime import date

import pytest
from django.utils import timezone

from meetings.models import ActionItem, AgendaItem, Meeting

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("collection,member,text", [("agenda", "presenter_id", "topic"), ("actions", "owner_id", "content")])
@pytest.mark.parametrize("missing", ["member", "text", "both"])
def test_patch_new_child_requires_fields(api, group, manager, collection, member, text, missing):
    meeting = Meeting.objects.create(group=group, created_by=manager, date=date(2026, 11, 18))
    agenda = AgendaItem.objects.create(meeting=meeting, presenter=manager, topic="original")
    action = ActionItem.objects.create(meeting=meeting, owner=manager, content="original")
    child = {member: manager.pk, text: "new"}
    if missing in ("member", "both"):
        child.pop(member)
    if missing in ("text", "both"):
        child.pop(text)
    response = api(manager).patch(f"/api/meetings/{meeting.pk}/", {collection: [child]}, format="json")
    assert response.status_code == 400
    errors = response.data["errors"][collection][0]
    expected = {member, text} if missing == "both" else {member if missing == "member" else text}
    assert set(errors) == expected
    assert all(error.code == "required" for values in errors.values() for error in values)
    assert list(meeting.agenda.values_list("pk", "topic")) == [(agenda.pk, "original")]
    assert list(meeting.actions.values_list("pk", "content")) == [(action.pk, "original")]


def test_patch_valid_new_children_and_partial_existing_item(api, group, manager):
    meeting = Meeting.objects.create(group=group, created_by=manager, date=date(2026, 11, 18))
    action = ActionItem.objects.create(meeting=meeting, owner=manager, content="original", done_at=timezone.now())
    completed_at = action.done_at
    client = api(manager)
    response = client.patch(f"/api/meetings/{meeting.pk}/", {
        "agenda": [{"presenter_id": manager.pk, "topic": "presentation"}],
        "actions": [{"id": action.pk, "content": "edited"}, {"owner_id": manager.pk, "content": "new"}],
    }, format="json")
    assert response.status_code == 200
    action.refresh_from_db()
    assert (action.content, action.owner_id, action.done_at) == ("edited", manager.pk, completed_at)
    assert meeting.actions.count() == 2
    assert meeting.agenda.get().topic == "presentation"
    response = client.patch(f"/api/meetings/{meeting.pk}/", {"title": "new title"}, format="json")
    assert response.status_code == 200
    assert meeting.actions.count() == 2 and meeting.agenda.count() == 1


@pytest.mark.parametrize("collection,member,text", [("agenda", "presenter_id", "topic"), ("actions", "owner_id", "content")])
@pytest.mark.parametrize("bad", [None, ""])
def test_patch_new_child_still_rejects_null_or_blank(api, group, manager, collection, member, text, bad):
    meeting = Meeting.objects.create(group=group, created_by=manager, date=date(2026, 11, 18))
    response = api(manager).patch(f"/api/meetings/{meeting.pk}/", {
        collection: [{member: manager.pk, text: bad}],
    }, format="json")
    assert response.status_code == 400
    assert text in response.data["errors"][collection][0]
    assert meeting.actions.count() == meeting.agenda.count() == 0
