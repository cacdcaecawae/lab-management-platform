"""Phase-1 acceptance criteria (docs/development-plan.md) exercised across all apps through the HTTP API."""

import hashlib

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

pytestmark = pytest.mark.django_db

RAW = b"\x00\x01guided-wave raw signal" * 1000


def upload(client, dataset_id, name, content):
    return client.post(f"/api/datasets/{dataset_id}/files/", {"file": SimpleUploadedFile(name, content)}, format="multipart")


def test_research_record_chain_review_flow_and_isolation(
    api, project, student_a, student_b, manager, advisor, other_manager
):
    a = api(student_a)

    # Datasets: raw data, script, result. Raw file stored with a matching checksum.
    raw = a.post("/api/datasets/", {"project_id": project.id, "name": "预紧力对比", "kind": "raw"}, format="json").json()
    script = a.post("/api/datasets/", {"project_id": project.id, "name": "CFWD", "kind": "script"}, format="json").json()
    result = a.post("/api/datasets/", {"project_id": project.id, "name": "结果", "kind": "result"}, format="json").json()
    r = upload(a, raw["id"], "baseline_01.mat", RAW)
    assert r.status_code == 201
    raw_file = r.json()[0]
    assert raw_file["sha256"] == hashlib.sha256(RAW).hexdigest()
    assert upload(a, script["id"], "CFWD_analysis.m", b"disp(1)").status_code == 201
    assert upload(a, result["id"], "result_summary.csv", b"a,b\n1,2\n").status_code == 201

    # Same name again: 409, original content untouched.
    r = upload(a, raw["id"], "baseline_01.mat", b"overwrite attempt")
    assert r.status_code == 409 and r.json()["code"] == "file_exists"
    assert b"".join(a.get(raw_file["download_url"]).streaming_content) == RAW

    # Experiment and processing run reference the datasets; both can be submitted.
    exp = a.post(
        "/api/experiments/",
        {"project_id": project.id, "title": "低预紧力重复实验", "date": "2026-11-16", "params": {"freq_khz": 200}, "dataset_ids": [raw["id"]]},
        format="json",
    ).json()
    assert a.post(f"/api/experiments/{exp['id']}/submit/").status_code == 200
    run = a.post(
        "/api/runs/",
        {
            "project_id": project.id, "title": "导波信号分析", "input_ids": [raw["id"]], "script_dataset_id": script["id"],
            "method_version": "v1.2", "params": {"band_khz": [150, 250]}, "environment": "MATLAB R2024b",
            "output_dataset_id": result["id"],
        },
        format="json",
    ).json()
    assert a.post(f"/api/runs/{run['id']}/submit/").status_code == 200
    run = a.get(f"/api/runs/{run['id']}/").json()
    # One record answers "how was this produced": inputs, script version, params, environment, outputs.
    assert [d["id"] for d in run["inputs"]] == [raw["id"]]
    assert run["script_dataset"]["id"] == script["id"] and run["method_version"] == "v1.2"
    assert run["params"] == {"band_khz": [150, 250]} and run["environment"] == "MATLAB R2024b"
    assert run["output_dataset"]["id"] == result["id"]

    # Weekly report: submit -> needs revision -> edit -> resubmit -> reviewed.
    report = a.post(
        "/api/reports/",
        {"week_start": "2026-11-16", "goals": "识别敏感频带", "experiment_ids": [exp["id"]], "dataset_ids": [raw["id"]], "run_ids": [run["id"]]},
        format="json",
    ).json()
    rid = report["id"]
    assert a.post(f"/api/reports/{rid}/submit/").status_code == 200
    r = api(advisor).post(f"/api/reports/{rid}/feedback/", {"verdict": "needs_revision", "content": "补充重复性分析"}, format="json")
    assert r.json()["status"] == "needs_revision"
    assert a.patch(f"/api/reports/{rid}/", {"findings": "三组重复实验结果一致"}, format="json").status_code == 200
    assert a.post(f"/api/reports/{rid}/submit/").status_code == 200
    r = api(advisor).post(f"/api/reports/{rid}/feedback/", {"verdict": "reviewed", "content": ""}, format="json")
    assert r.json()["status"] == "reviewed" and len(r.json()["feedback"]) == 2
    history = a.get(f"/api/reports/{rid}/history/").json()
    assert any(c["field"] == "findings" for entry in history for c in entry["changes"])

    # Isolation: a classmate, a classmate with the 管理员 tag and the other group's manager get 404 on every private
    # URL, including downloads; the group's advisor reads them.
    private_urls = [
        f"/api/datasets/{raw['id']}/", f"/api/datasets/{raw['id']}/files/", f"/api/files/{raw_file['id']}/",
        raw_file["download_url"], f"/api/experiments/{exp['id']}/", f"/api/experiments/{exp['id']}/history/",
        f"/api/runs/{run['id']}/", f"/api/reports/{rid}/", f"/api/reports/{rid}/history/",
    ]
    for outsider in (student_b, manager, other_manager):
        client = api(outsider)
        for url in private_urls:
            assert client.get(url).status_code == 404, (outsider.username, url)
        assert client.get("/api/experiments/").json()["count"] == 0
    client = api(advisor)
    for url in private_urls:
        assert client.get(url).status_code == 200, (advisor.username, url)


def test_list_filters_do_not_hide_detail(api, project, student_a):
    url = f"/api/projects/{project.id}/?status=closed&mine=1"
    assert api(student_a).get(url).status_code == 200


def test_concurrent_duplicate_project_name_is_409_not_500(api, project, manager, monkeypatch):
    from projects.serializers import ProjectSerializer

    # Simulate the race: the pre-check passed, then the unique constraint fires.
    monkeypatch.setattr(ProjectSerializer, "validate_name", lambda self, value: value)
    r = api(manager).post("/api/projects/", {"name": project.name, "leader_id": manager.id}, format="json")
    assert r.status_code == 409 and r.json()["code"] == "conflict"
