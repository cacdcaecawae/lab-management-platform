from datetime import date, timedelta

import pytest
from django.utils import timezone

from conftest import make_user
from datasets.models import Dataset
from reports.models import ReportFeedback, WeeklyReport
from research.models import Experiment, ProcessingRun

pytestmark = pytest.mark.django_db

URL = "/api/reports/"
MONDAY = date(2026, 11, 16)
S = WeeklyReport.Status


def report(owner, week_start=MONDAY, **fields):
    return WeeklyReport.objects.create(owner=owner, week_start=week_start, **fields)


def url(r, suffix=""):
    return f"{URL}{r.id if hasattr(r, 'id') else r}/{suffix}"


# --- end-to-end ---------------------------------------------------------------------------------


def test_full_review_flow(api, project, student_a, manager, advisor):
    exp = Experiment.objects.create(owner=student_a, project=project, title="重复性实验", date=MONDAY)
    ds = Dataset.objects.create(owner=student_a, project=project, name="原始波形")
    run = ProcessingRun.objects.create(owner=student_a, project=project, title="包络提取")
    student = api(student_a)

    r = student.post(URL, {
        "week_start": "2026-11-16", "goals": "完成重复性实验", "done": "做了 3 组",
        "experiment_ids": [exp.id], "dataset_ids": [ds.id], "run_ids": [run.id],
    }, format="json")
    assert r.status_code == 201, r.data
    rid = r.data["id"]
    assert r.data["status"] == "draft" and r.data["owner"] == {"id": student_a.id, "name": "s_a"}
    assert r.data["experiments"] == [{"id": exp.id, "code": exp.code, "title": "重复性实验", "status": "draft"}]
    assert [d["id"] for d in r.data["datasets"]] == [ds.id] and [x["id"] for x in r.data["runs"]] == [run.id]
    assert "experiment_ids" not in r.data

    r = student.post(url(rid, "submit/"))
    assert r.status_code == 200 and r.data["status"] == "submitted" and r.data["submitted_at"]
    first_submitted_at = r.data["submitted_at"]

    r = api(manager).post(url(rid, "feedback/"), {"verdict": "needs_revision", "content": "补充第 2 组数据"}, format="json")
    assert r.status_code == 200, r.data
    assert r.data["status"] == "needs_revision" and len(r.data["feedback"]) == 1
    assert r.data["feedback"][0]["author"] == {"id": manager.id, "name": "mgr"}

    r = student.patch(url(rid), {"done": "做了 3 组，补充第 2 组"}, format="json")
    assert r.status_code == 200 and r.data["done"] == "做了 3 组，补充第 2 组"
    assert [e["id"] for e in r.data["experiments"]] == [exp.id]  # untouched links stay

    r = student.post(url(rid, "submit/"))
    assert r.status_code == 200 and r.data["status"] == "submitted"
    assert r.data["submitted_at"] != first_submitted_at

    r = api(advisor).post(url(rid, "feedback/"), {"verdict": "reviewed"}, format="json")
    assert r.status_code == 200, r.data
    assert r.data["status"] == "reviewed"
    assert [(f["author"]["id"], f["verdict"]) for f in r.data["feedback"]] == [
        (manager.id, "needs_revision"), (advisor.id, "reviewed"),
    ]

    history = student.get(url(rid, "history/")).data
    oldest_first = list(reversed(history))
    assert [h["type"] for h in oldest_first] == ["created"] + ["changed"] * 5
    changed = [{c["field"]: c["new"] for c in h["changes"]} for h in oldest_first[1:]]
    assert [c.get("status") for c in changed] == ["submitted", "needs_revision", None, "submitted", "reviewed"]
    assert changed[2]["done"] == "做了 3 组，补充第 2 组"
    assert [h["user"]["id"] for h in oldest_first] == [student_a.id] * 2 + [manager.id] + [student_a.id] * 2 + [advisor.id]


# --- create / update / delete -------------------------------------------------------------------


def test_week_start_must_be_monday(api, student_a):
    r = api(student_a).post(URL, {"week_start": "2026-11-17"}, format="json")
    assert r.status_code == 400 and "week_start" in r.data["errors"]


def test_duplicate_week_is_conflict(api, student_a):
    report(student_a)
    r = api(student_a).post(URL, {"week_start": "2026-11-16"}, format="json")
    assert r.status_code == 409 and r.data["code"] == "conflict"


@pytest.mark.parametrize("field", ["experiment_ids", "dataset_ids", "run_ids"])
def test_cannot_link_other_peoples_records(api, project, student_a, student_b, field):
    others = {
        "experiment_ids": lambda: Experiment.objects.create(owner=student_b, project=project, title="b", date=MONDAY),
        "dataset_ids": lambda: Dataset.objects.create(owner=student_b, project=project, name="b"),
        "run_ids": lambda: ProcessingRun.objects.create(owner=student_b, project=project, title="b"),
    }[field]()
    student = api(student_a)
    r = student.post(URL, {"week_start": "2026-11-16", field: [others.id]}, format="json")
    assert r.status_code == 400 and field in r.data["errors"]

    mine = report(student_a, week_start=MONDAY - timedelta(days=7))
    r = student.patch(url(mine), {field: [others.id]}, format="json")
    assert r.status_code == 400 and field in r.data["errors"]


@pytest.mark.parametrize("state", [S.SUBMITTED, S.REVIEWED])
def test_patch_after_submit_is_invalid_state(api, student_a, state):
    r = api(student_a).patch(url(report(student_a, status=state)), {"done": "x"}, format="json")
    assert r.status_code == 409 and r.data["code"] == "invalid_state"


def test_week_start_cannot_change(api, student_a):
    r = api(student_a).patch(url(report(student_a)), {"week_start": "2026-11-23"}, format="json")
    assert r.status_code == 400 and "week_start" in r.data["errors"]


def test_supervisor_cannot_edit_or_submit_students_report(api, student_a, manager):
    mine = report(student_a)
    assert api(manager).patch(url(mine), {"done": "x"}, format="json").status_code == 403
    assert api(manager).post(url(mine, "submit/")).status_code == 403
    assert api(manager).delete(url(mine)).status_code == 403


def test_delete_only_draft(api, student_a):
    student = api(student_a)
    assert student.delete(url(report(student_a, week_start=MONDAY, status=S.SUBMITTED))).status_code == 409
    draft = report(student_a, week_start=MONDAY - timedelta(days=7))
    assert student.delete(url(draft)).status_code == 204
    assert not WeeklyReport.objects.filter(pk=draft.pk).exists()


def test_submit_twice_is_invalid_state(api, student_a):
    r = api(student_a).post(url(report(student_a, status=S.SUBMITTED), "submit/"))
    assert r.status_code == 409 and r.data["code"] == "invalid_state"


# --- feedback -----------------------------------------------------------------------------------


def test_student_cannot_give_feedback(api, student_a, student_b):
    r = api(student_b).post(url(report(student_a, status=S.SUBMITTED), "feedback/"), {"verdict": "reviewed"}, format="json")
    assert r.status_code == 403


def test_supervisor_cannot_review_own_report(api, manager):
    r = api(manager).post(url(report(manager, status=S.SUBMITTED), "feedback/"), {"verdict": "reviewed"}, format="json")
    assert r.status_code == 403


def test_feedback_only_on_submitted(api, student_a, manager):
    r = api(manager).post(url(report(student_a), "feedback/"), {"verdict": "reviewed"}, format="json")
    assert r.status_code == 409 and r.data["code"] == "invalid_state"
    assert not ReportFeedback.objects.exists()


def test_needs_revision_requires_content(api, student_a, manager):
    target = report(student_a, status=S.SUBMITTED)
    r = api(manager).post(url(target, "feedback/"), {"verdict": "needs_revision", "content": "  "}, format="json")
    assert r.status_code == 400 and "content" in r.data["errors"]
    target.refresh_from_db()
    assert target.status == S.SUBMITTED and not target.feedback.exists()


def test_long_feedback_content(api, student_a, manager):
    r = api(manager).post(url(report(student_a, status=S.SUBMITTED), "feedback/"), {"verdict": "needs_revision", "content": "补" * 300}, format="json")
    assert r.status_code == 200 and r.data["feedback"][0]["content"] == "补" * 300


def test_unknown_verdict_rejected(api, student_a, manager):
    r = api(manager).post(url(report(student_a, status=S.SUBMITTED), "feedback/"), {"verdict": "submitted"}, format="json")
    assert r.status_code == 400 and "verdict" in r.data["errors"]


# --- missing ------------------------------------------------------------------------------------


def test_missing_lists_students_without_handed_in_report(api, group, other_group, student_a, student_b, manager, advisor):
    student_c = make_user("s_c", group)
    gone = make_user("s_gone", group, is_active=False)
    outsider = make_user("s_out", other_group)
    report(student_a, status=S.SUBMITTED)
    report(student_b)  # a draft does not count
    report(student_b, week_start=MONDAY - timedelta(days=7), status=S.SUBMITTED)  # last week does not count
    report(student_c, status=S.NEEDS_REVISION)

    r = api(manager).get(f"{URL}missing/", {"week_start": "2026-11-16"})
    assert r.status_code == 200
    assert r.data == [{"id": student_b.id, "name": "s_b"}]
    ids = {u["id"] for u in r.data}
    assert gone.id not in ids and outsider.id not in ids and advisor.id not in ids


def test_missing_defaults_to_this_week(api, student_a, student_b, advisor):
    today = timezone.localdate()
    report(student_a, week_start=today - timedelta(days=today.weekday()), status=S.REVIEWED)
    r = api(advisor).get(f"{URL}missing/")
    assert r.status_code == 200 and r.data == [{"id": student_b.id, "name": "s_b"}]


def test_missing_rejects_non_monday_and_students(api, student_a, manager):
    assert api(manager).get(f"{URL}missing/", {"week_start": "2026-11-18"}).status_code == 400
    assert api(student_a).get(f"{URL}missing/").status_code == 403


# --- list / isolation ---------------------------------------------------------------------------


def test_list_scope_and_filters(api, student_a, student_b, manager, other_manager):
    a = report(student_a, status=S.SUBMITTED)
    b = report(student_b)
    assert [x["id"] for x in api(student_a).get(URL).data["results"]] == [a.id]
    assert {x["id"] for x in api(manager).get(URL).data["results"]} == {a.id, b.id}
    assert [x["id"] for x in api(manager).get(URL, {"status": "submitted"}).data["results"]] == [a.id]
    assert [x["id"] for x in api(manager).get(URL, {"owner": student_b.id}).data["results"]] == [b.id]
    assert api(manager).get(URL, {"week_start": "2026-11-09"}).data["count"] == 0
    assert api(other_manager).get(URL).data["count"] == 0
    assert api(manager).get(URL, {"owner": "abc"}).status_code == 400
    assert api(manager).get(URL, {"status": "nope"}).status_code == 400


def test_list_query_count_does_not_grow(api, project, group, manager, django_assert_max_num_queries):
    for i in range(5):
        owner = make_user(f"s_{i}", group)
        r = report(owner, status=S.SUBMITTED)
        r.experiments.add(Experiment.objects.create(owner=owner, project=project, title="e", date=MONDAY))
        r.datasets.add(Dataset.objects.create(owner=owner, project=project, name="d"))
        r.runs.add(ProcessingRun.objects.create(owner=owner, project=project, title="r"))
        ReportFeedback.objects.create(report=r, author=manager, verdict="reviewed")
    client = api(manager)
    with django_assert_max_num_queries(10):
        assert client.get(URL).data["count"] == 5


def test_student_cannot_touch_other_students_report(api, student_a, student_b):
    theirs = report(student_b)
    student = api(student_a)
    assert student.get(url(theirs)).status_code == 404
    assert student.patch(url(theirs), {"done": "x"}, format="json").status_code == 404
    assert student.delete(url(theirs)).status_code == 404
    assert student.post(url(theirs, "submit/")).status_code == 404
    assert student.get(url(theirs, "history/")).status_code == 404
    theirs.refresh_from_db()
    assert theirs.status == S.DRAFT and theirs.done == ""


def test_other_group_supervisor_gets_404(api, student_a, other_manager):
    target = report(student_a, status=S.SUBMITTED)
    client = api(other_manager)
    assert client.get(url(target)).status_code == 404
    assert client.get(url(target, "history/")).status_code == 404
    assert client.post(url(target, "feedback/"), {"verdict": "reviewed"}, format="json").status_code == 404


def test_group_supervisors_can_read(api, student_a, manager, advisor):
    target = report(student_a)
    for user in (manager, advisor):
        client = api(user)
        assert client.get(url(target)).data["id"] == target.id
        assert client.get(url(target, "history/")).status_code == 200
