import io
import zipfile
from pathlib import Path

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import load_workbook

from achievements.models import Achievement
from conftest import make_user

pytestmark = pytest.mark.django_db


def register(client, **extra):
    body = {
        "type": "paper", "title": "螺栓预紧力的导波评估", "authors": "学生甲, 学生乙, 外单位丙", "venue": "NDT&E International",
        "date": "2025-06-01", "status": "accepted", **extra,
    }
    return client.post("/api/achievements/", body, format="json")


def pdf(content=b"%PDF-1.4 paper"):
    return SimpleUploadedFile("paper.pdf", content, content_type="application/pdf")


def test_register_and_who_may_change_it(api, group, student_a, student_b, manager, other_manager):
    r = register(api(student_a), member_ids=[student_a.id, student_b.id])
    assert r.status_code == 201 and sorted(m["id"] for m in r.data["members"]) == sorted([student_a.id, student_b.id])
    aid = r.data["id"]
    assert Achievement.objects.get().group == group
    assert [x["id"] for x in api(manager).get("/api/achievements/", {"member": student_b.id}).data["results"]] == [aid]
    assert api(manager).get("/api/achievements/", {"member": manager.id}).data["count"] == 0
    assert register(api(student_a), type="patent", status="accepted").data["errors"]["status"] == ["专利的状态只能是：申请中、已授权"]
    assert api(other_manager).get(f"/api/achievements/{aid}/").status_code == 404

    outsider = make_user("s_c", group)
    assert api(outsider).get(f"/api/achievements/{aid}/").status_code == 200  # group-wide read
    assert api(outsider).patch(f"/api/achievements/{aid}/", {"status": "published"}, format="json").status_code == 403
    assert api(student_b).patch(f"/api/achievements/{aid}/", {"status": "published"}, format="json").status_code == 200
    assert api(student_b).patch(f"/api/achievements/{aid}/", {"status": "granted"}, format="json").status_code == 400

    student_b.is_active = False  # graduated: still an author of the record
    student_b.save()
    r = api(student_a).patch(f"/api/achievements/{aid}/", {"member_ids": [student_a.id, student_b.id], "notes": "终版"}, format="json")
    assert r.status_code == 200

    assert api(student_a).delete(f"/api/achievements/{aid}/").status_code == 403  # only managers delete
    assert api(manager).delete(f"/api/achievements/{aid}/").status_code == 204


def test_fulltext(api, django_capture_on_commit_callbacks, student_a, student_b, other_manager):
    aid = register(api(student_a)).data["id"]
    url = f"/api/achievements/{aid}/fulltext/"
    assert api(student_a).get(url).status_code == 404
    assert api(student_a).post(url, {"file": SimpleUploadedFile("paper.docx", b"PK")}).status_code == 400  # PDF only
    assert api(student_b).post(url, {"file": pdf()}).status_code == 403  # not an author
    r = api(student_a).post(url, {"file": pdf()})
    assert r.status_code == 200 and r.data["fulltext_name"] == "paper.pdf" and r.data["fulltext_url"] == url
    first = Path(settings.MEDIA_ROOT) / Achievement.objects.get().fulltext.name

    with django_capture_on_commit_callbacks(execute=True):
        api(student_a).post(url, {"file": pdf(b"%PDF-1.4 final")})
    assert not first.exists()  # replaced: the old file is gone, the new one is served
    r = api(student_b).get(url)
    assert b"".join(r.streaming_content) == b"%PDF-1.4 final" and r["Content-Disposition"].startswith("inline")
    assert api(other_manager).get(url).status_code == 404

    second = Path(settings.MEDIA_ROOT) / Achievement.objects.get().fulltext.name
    with django_capture_on_commit_callbacks(execute=True):
        assert api(student_a).delete(url).data["fulltext_url"] is None
    assert not second.exists()


@pytest.mark.django_db(transaction=True)  # the clean-up runs at a real commit, not in a test savepoint
def test_replacing_keeps_the_new_file_when_the_old_one_cannot_be_removed(api, student_a, monkeypatch):
    from django.core.files.storage import FileSystemStorage

    aid = register(api(student_a)).data["id"]
    url = f"/api/achievements/{aid}/fulltext/"
    api(student_a).post(url, {"file": pdf(b"%PDF-1.4 draft")})
    old = Achievement.objects.get().fulltext.name
    delete = FileSystemStorage.delete

    def locked(storage, name):  # e.g. a virus scanner holding the old file open on Windows
        if name == old:
            raise PermissionError(name)
        return delete(storage, name)

    monkeypatch.setattr(FileSystemStorage, "delete", locked)
    assert api(student_a).post(url, {"file": pdf(b"%PDF-1.4 final")}).status_code == 200
    kept = Achievement.objects.get().fulltext
    assert kept.name != old and kept.read() == b"%PDF-1.4 final"  # the saved record still has its file


def test_export_a_years_accepted_papers_with_full_texts(api, student_a, manager, other_manager):
    a = api(student_a)
    with_text = {}
    for title, status in (("论文一", "accepted"), ("论文二", "published")):
        aid = register(a, title=title, status=status).data["id"]
        a.post(f"/api/achievements/{aid}/fulltext/", {"file": pdf(f"%PDF {title}".encode())})
        with_text[title] = f"%PDF {title}".encode()
    register(a, title="还在投", status="submitted")
    register(a, title="去年的", date="2024-05-01")
    register(a, type="patent", title="一种螺栓检测装置", status="granted", venue="ZL2025xxxx")

    query = {"type": "paper", "year": "2025", "status": "accepted,published"}
    listed = a.get("/api/achievements/", query).data
    assert sorted(r["title"] for r in listed["results"]) == ["论文一", "论文二"]

    table = load_workbook(io.BytesIO(a.get("/api/achievements/export/", query).content))["成果清单"]
    assert [row[2] for row in table.iter_rows(min_row=2, values_only=True)] == ["论文一", "论文二"]

    r = a.get("/api/achievements/export/", {**query, "files": "1"})
    assert r.status_code == 200 and r["Content-Disposition"].startswith("attachment")
    archive = zipfile.ZipFile(io.BytesIO(b"".join(r.streaming_content)))
    rows = list(load_workbook(io.BytesIO(archive.read("成果清单.xlsx")))["成果清单"].iter_rows(min_row=2, values_only=True))
    assert len(rows) == listed["count"]
    for row in rows:  # each row names its full text in the archive
        assert archive.read(row[9]) == with_text[row[2]]
    assert a.get("/api/achievements/export/", {"status": "nope"}).status_code == 400

    register(a, title='=HYPERLINK("http://example.com","点我")')
    title = load_workbook(io.BytesIO(a.get("/api/achievements/export/", {"search": "HYPERLINK"}).content))["成果清单"]["C2"]
    assert title.value.startswith("=HYPERLINK") and title.data_type == "s"

    # another group's export: the header row and nothing else, no full texts
    r = api(other_manager).get("/api/achievements/export/", {"files": "1"})
    archive = zipfile.ZipFile(io.BytesIO(b"".join(r.streaming_content)))
    assert archive.namelist() == ["成果清单.xlsx"]
    assert load_workbook(io.BytesIO(archive.read("成果清单.xlsx")))["成果清单"].max_row == 1
