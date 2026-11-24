from pathlib import Path

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile

from meetings.models import ActionItem, Meeting, MeetingFile
from meetings.views import MeetingViewSet

pytestmark = pytest.mark.django_db


def body(student_a, student_b, **extra):
    return {
        "date": "2026-11-20",
        "agenda": [{"presenter_id": student_a.id, "topic": "导波螺栓松动：重复性"}],
        "actions": [
            {"owner_id": student_b.id, "content": "补测 3 号试件", "due_date": "2026-11-27"},
            {"owner_id": student_b.id, "content": "整理标定数据"},
        ],
        **extra,
    }


@pytest.fixture
def meeting(api, manager, student_a, student_b):
    r = api(manager).post("/api/meetings/", body(student_a, student_b), format="json")
    assert r.status_code == 201
    return r.data


def test_advisors_and_managers_run_meetings(api, group, student_a, student_b, advisor, other_manager, meeting):
    assert api(student_a).post("/api/meetings/", body(student_a, student_b), format="json").status_code == 403
    assert Meeting.objects.get().group == group and meeting["title"] == "组会"
    assert api(advisor).post("/api/meetings/", body(student_a, student_b), format="json").status_code == 201  # issue #48 N4
    r = api(student_b).get(f"/api/meetings/{meeting['id']}/")  # group-wide read
    assert r.data["agenda"][0]["presenter"]["id"] == student_a.id and len(r.data["actions"]) == 2
    assert api(other_manager).get(f"/api/meetings/{meeting['id']}/").status_code == 404
    assert api(student_a).patch(f"/api/meetings/{meeting['id']}/", {"minutes": "x"}, format="json").status_code == 403


def test_editing_a_meeting_keeps_what_is_done(api, manager, student_a, student_b, meeting):
    first, second = meeting["actions"]
    assert api(student_a).post(f"/api/action-items/{first['id']}/done/", {"done": True}).status_code == 403  # not theirs
    r = api(student_b).post(f"/api/action-items/{first['id']}/done/", {"done": True})
    assert r.status_code == 200 and r.data["done_at"]

    actions = [
        {"id": first["id"], "owner_id": student_b.id, "content": "补测 3、4 号试件", "due_date": "2026-11-28"},
        {"owner_id": student_a.id, "content": "改图"},
    ]
    r = api(manager).patch(f"/api/meetings/{meeting['id']}/", {"actions": actions, "minutes": "结论：重复性达标"}, format="json")
    assert r.status_code == 200 and r.data["minutes"] == "结论：重复性达标"
    kept = ActionItem.objects.get(pk=first["id"])
    assert kept.content == "补测 3、4 号试件" and kept.done_at is not None  # still done
    assert not ActionItem.objects.filter(pk=second["id"]).exists()  # left out: removed
    assert [a["content"] for a in r.data["actions"]] == ["补测 3、4 号试件", "改图"]
    bad = [{"id": 99999, "owner_id": student_a.id, "content": "x"}]
    assert api(manager).patch(f"/api/meetings/{meeting['id']}/", {"actions": bad}, format="json").status_code == 400


def test_workbench_lists_my_open_action_items(api, student_b, meeting):
    first, second = meeting["actions"]
    items = api(student_b).get("/api/dashboard/").data["my"]["action_items"]
    assert [i["id"] for i in items] == [first["id"], second["id"]]  # due date first, none last
    assert items[0]["meeting"] == {"id": meeting["id"], "date": "2026-11-20", "title": "组会"}
    api(student_b).post(f"/api/action-items/{first['id']}/done/", {"done": True})
    assert [i["id"] for i in api(student_b).get("/api/dashboard/").data["my"]["action_items"]] == [second["id"]]


def test_presenters_upload_files(api, django_capture_on_commit_callbacks, manager, student_a, student_b, other_manager, meeting):
    url = f"/api/meetings/{meeting['id']}/files/"
    slides = SimpleUploadedFile("汇报.pptx", b"PK slides")
    assert api(student_b).post(url, {"file": slides}).status_code == 403  # not on the agenda
    r = api(student_a).post(url, {"file": SimpleUploadedFile("汇报.pptx", b"PK slides")})
    assert r.status_code == 201 and r.data["name"] == "汇报.pptx"
    download = api(student_b).get(r.data["url"])
    assert download.status_code == 200 and download["Content-Disposition"].startswith("attachment")
    assert b"".join(download.streaming_content) == b"PK slides"  # read to the end, which also closes the file
    assert api(other_manager).get(r.data["url"]).status_code == 404
    assert api(student_b).delete(f"/api/meeting-files/{r.data['id']}/").status_code == 403

    stored = Path(settings.MEDIA_ROOT) / MeetingFile.objects.get().file.name
    with django_capture_on_commit_callbacks(execute=True):
        assert api(manager).delete(f"/api/meetings/{meeting['id']}/").status_code == 204
    assert not MeetingFile.objects.exists() and not stored.exists()


def test_deleting_a_meeting_removes_a_file_uploaded_just_before(
    api, monkeypatch, django_capture_on_commit_callbacks, manager, student_a, meeting
):
    get_object = MeetingViewSet.get_object

    def then_uploaded(view):
        found = get_object(view)  # its files are fetched with it: none yet
        if view.action != "destroy":
            return found
        assert api(student_a).post(f"/api/meetings/{found.pk}/files/", {"file": SimpleUploadedFile("a.pptx", b"PK")}).status_code == 201
        return found

    monkeypatch.setattr(MeetingViewSet, "get_object", then_uploaded)
    with django_capture_on_commit_callbacks(execute=True):
        assert api(manager).delete(f"/api/meetings/{meeting['id']}/").status_code == 204
    assert not [p for p in Path(settings.MEDIA_ROOT).rglob("*") if p.is_file()]
