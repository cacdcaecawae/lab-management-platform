"""Issue #58 P4-3: a meeting's time, place and recorder; the recorder writes the minutes and action items; advisors tick
action items done."""
import pytest

from meetings.models import ActionItem, Meeting

pytestmark = pytest.mark.django_db


@pytest.fixture
def meeting(api, advisor, student_a, student_b):
    r = api(advisor).post("/api/meetings/", {
        "date": "2026-11-20", "time": "19:00", "location": "腾讯会议 123-456-789", "recorder_id": student_b.id,
        "agenda": [{"presenter_id": student_a.id, "topic": "重复性"}],
        "actions": [{"owner_id": student_a.id, "content": "补测 3 号试件"}],
    }, format="json")
    assert r.status_code == 201, r.data
    return r.data


def test_time_place_and_recorder(api, group, student_b, other_manager, other_advisor, meeting):
    assert meeting["time"] == "19:00" and meeting["location"] == "腾讯会议 123-456-789"
    assert meeting["recorder"] == {"id": student_b.id, "name": "s_b"}
    assert Meeting.objects.get().recorder == student_b
    r = api(other_advisor).post("/api/meetings/", {"date": "2026-11-20", "recorder_id": student_b.id}, format="json")
    assert r.status_code == 400 and "recorder_id" in r.data["errors"]  # not their group's member
    assert api(other_manager).patch(f"/api/meetings/{meeting['id']}/", {"minutes": "x"}, format="json").status_code == 404
    bare = api(other_advisor).post("/api/meetings/", {"date": "2026-11-21"}, format="json").data
    assert bare["time"] is None and bare["location"] == "" and bare["recorder"] is None


def test_the_recorder_writes_minutes_and_action_items_only(api, student_a, student_b, manager, meeting):
    url = f"/api/meetings/{meeting['id']}/"
    item = meeting["actions"][0]
    recorder = api(student_b)
    r = recorder.patch(url, {
        "minutes": "讨论了重复性",
        "actions": [{"id": item["id"], "owner_id": student_a.id, "content": "补测 3、4 号试件"},
                    {"owner_id": student_b.id, "content": "整理纪要"}],
    }, format="json")
    assert r.status_code == 200, r.data
    assert r.data["minutes"] == "讨论了重复性" and [a["content"] for a in r.data["actions"]] == ["补测 3、4 号试件", "整理纪要"]

    for field, value in (("title", "改标题"), ("date", "2026-11-21"), ("recorder_id", student_a.id),
                         ("agenda", []), ("location", "别处")):
        refused = recorder.patch(url, {"minutes": "x", field: value}, format="json")
        assert refused.status_code == 403 and refused.data["message"] == "记录人只能编辑纪要和行动项", field
    other = api(student_a).patch(url, {"minutes": "x"}, format="json")  # a presenter, not the recorder
    assert other.status_code == 403 and other.data["message"] == "仅导师、管理员或本场记录人可以编辑组会"
    assert recorder.delete(url).status_code == 403
    assert api(manager).patch(url, {"title": "第 12 次组会", "recorder_id": None}, format="json").status_code == 200
    assert recorder.patch(url, {"minutes": "y"}, format="json").status_code == 403  # no longer the recorder
    assert Meeting.objects.get().minutes == "讨论了重复性"


def test_advisors_tick_action_items(api, student_a, student_b, advisor, manager, other_advisor, meeting):
    done = f"/api/action-items/{meeting['actions'][0]['id']}/done/"
    r = api(advisor).post(done, {"done": True}, format="json")
    assert r.status_code == 200 and r.data["done_at"]
    assert api(manager).post(done, {"done": False}, format="json").data["done_at"] is None
    refused = api(student_b).post(done, {"done": True}, format="json")  # the recorder, not the item's owner
    assert refused.status_code == 403 and refused.data["message"] == "只有负责人、导师和管理员可以修改完成状态"
    assert api(other_advisor).post(done, {"done": True}, format="json").status_code == 404
    assert api(student_a).post(done, {"done": True}, format="json").status_code == 200  # the owner
    assert ActionItem.objects.get().done_at
