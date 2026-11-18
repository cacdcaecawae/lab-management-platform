import hashlib
from pathlib import Path

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile

from equipment.models import Equipment
from knowledge.models import Doc, DocVersion

pytestmark = pytest.mark.django_db


@pytest.fixture
def device(group):
    return Equipment.objects.create(group=group, code="PA-001", name="相控阵超声仪", model="OmniScan X3")


def create(client, **extra):
    body = {"title": "OmniScan SDK 安装说明", "category": "sdk", "description": "先装驱动再装 SDK", **extra}
    return client.post("/api/docs/", body, format="json")


def upload(client, doc_id, name="sdk.zip", content=b"PK sdk v1", note=""):
    return client.post(f"/api/docs/{doc_id}/versions/", {"file": SimpleUploadedFile(name, content), "note": note})


def test_everyone_reads_and_creates_writers_are_limited(
    api, django_capture_on_commit_callbacks, group, student_a, student_b, manager, other_manager, device
):
    r = create(api(student_a), equipment_id=device.id, tags=[" SDK ", "驱动", "SDK", ""])
    assert r.status_code == 201 and r.data["author"]["id"] == student_a.id and r.data["tags"] == ["SDK", "驱动"]
    assert r.data["equipment"]["code"] == "PA-001" and r.data["versions"] == [] and r.data["latest"] is None
    doc_id = r.data["id"]
    assert Doc.objects.get(pk=doc_id).group == group
    assert api(student_b).get(f"/api/docs/{doc_id}/").status_code == 200  # group-wide
    assert api(other_manager).get(f"/api/docs/{doc_id}/").status_code == 404
    assert api(other_manager).get("/api/docs/").data["count"] == 0

    assert api(student_b).patch(f"/api/docs/{doc_id}/", {"title": "改"}, format="json").status_code == 403
    assert upload(api(student_b), doc_id).status_code == 403
    assert api(manager).patch(f"/api/docs/{doc_id}/", {"title": "SDK 安装说明"}, format="json").status_code == 200
    history = api(student_a).get(f"/api/docs/{doc_id}/history/").data
    assert {"field": "title", "old": "OmniScan SDK 安装说明", "new": "SDK 安装说明"} in history[0]["changes"]

    stored = Path(settings.MEDIA_ROOT) / DocVersion.objects.get(pk=upload(api(student_a), doc_id).data["id"]).file.name
    assert api(student_a).delete(f"/api/docs/{doc_id}/").status_code == 403  # only managers delete
    with django_capture_on_commit_callbacks(execute=True):
        assert api(manager).delete(f"/api/docs/{doc_id}/").status_code == 204
    assert not Doc.objects.exists() and not stored.exists()


def test_other_groups_equipment_is_refused(api, student_a, other_group):
    outside = Equipment.objects.create(group=other_group, code="X-1", name="外组设备")
    assert "equipment_id" in create(api(student_a), equipment_id=outside.id).data["errors"]


def test_new_versions_keep_the_earlier_files(api, student_a, manager, other_manager):
    doc_id = create(api(student_a)).data["id"]
    first = upload(api(student_a), doc_id, content=b"PK sdk v1", note="首次上传")
    assert first.status_code == 201 and first.data["number"] == 1
    assert first.data["sha256"] == hashlib.sha256(b"PK sdk v1").hexdigest()
    second = upload(api(manager), doc_id, content=b"PK sdk v2", note="适配新固件")
    assert second.status_code == 201 and second.data["number"] == 2

    doc = api(student_a).get(f"/api/docs/{doc_id}/").data
    assert [v["number"] for v in doc["versions"]] == [2, 1] and doc["latest"]["note"] == "适配新固件"
    for version, content in ((doc["versions"][1], b"PK sdk v1"), (doc["versions"][0], b"PK sdk v2")):
        r = api(student_a).get(version["url"])
        assert r.status_code == 200 and b"".join(r.streaming_content) == content
    assert api(other_manager).get(doc["versions"][0]["url"]).status_code == 404
    assert api(student_a).get(f"/api/docs/{doc_id}/versions/9/file/").status_code == 404


def test_only_pdf_and_images_open_in_the_browser(api, student_a):
    doc_id = create(api(student_a)).data["id"]
    page = upload(api(student_a), doc_id, name="notes.html", content=b"<script>alert(1)</script>").data
    assert api(student_a).get(page["url"])["Content-Disposition"].startswith("attachment")
    manual = upload(api(student_a), doc_id, name="手册.pdf", content=b"%PDF-1.4").data
    assert api(student_a).get(manual["url"])["Content-Disposition"].startswith("inline")


def test_search_finds_a_devices_sdk_and_manual(api, student_a, device):
    a = api(student_a)
    sdk = create(a, equipment_id=device.id).data["id"]
    manual = create(a, title="使用手册", category="manual", equipment_id=device.id, tags=["操作"]).data["id"]
    other = create(a, title="Python 处理模板", category="template", tags=["滤波"], description="带通滤波").data["id"]

    def found(**q):
        return sorted(d["id"] for d in a.get("/api/docs/", q).data["results"])

    assert found(search="PA-001") == found(search="相控阵") == sorted([sdk, manual])  # by the device
    assert found(search="滤") == [other]  # tag and description substrings
    assert found(search="手册") == [manual]
    assert found(category="manual") == [manual] and found(category="nope") == []
    assert found(equipment=device.id) == sorted([sdk, manual]) and found(equipment="x") == []
    assert found(tag="操作") == [manual]
    assert a.get(f"/api/docs/{other}/", {"category": "manual"}).status_code == 200  # filters do not hide details
