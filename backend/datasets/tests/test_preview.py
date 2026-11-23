import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from datasets.models import DataFile, Dataset

pytestmark = pytest.mark.django_db


def _upload(api, user, dataset, name, content, content_type="application/octet-stream"):
    r = api(user).post(
        f"/api/datasets/{dataset.pk}/files/",
        {"file": SimpleUploadedFile(name, content, content_type=content_type)},
        format="multipart",
    )
    assert r.status_code == 201, r.json()
    return r.json()[0]


def test_dataset_file_preview_text_csv_image_pdf_and_xss_blocks(api, tmp_path, settings, student_a, student_b, advisor, other_manager, project):
    settings.MEDIA_ROOT = str(tmp_path)
    ds = Dataset.objects.create(owner=student_a, project=project, name="超声波形数据集")

    # 1) GB18030 Chinese CSV with > 200 lines -> decoded cleanly and truncated at 200 lines
    csv_lines = ["时间_us,幅值_mV"] + [f"{i * 0.5},{i}" for i in range(250)]
    csv_file = _upload(api, student_a, ds, "wave.csv", "\n".join(csv_lines).encode("gb18030"), "text/csv")
    assert csv_file["preview_kind"] == "text"
    r = api(student_a).get(csv_file["preview_url"])
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "text" and body["format"] == "csv" and body["truncated"] is True and body["lines"] == 200
    assert body["content"].startswith("时间_us,幅值_mV")
    assert "private" in r["Cache-Control"]
    # Supervisor sees it; other student and other group get 404
    assert api(advisor).get(csv_file["preview_url"]).status_code == 200
    assert api(student_b).get(csv_file["preview_url"]).status_code == 404
    assert api(other_manager).get(csv_file["preview_url"]).status_code == 404

    # The byte cap can split a UTF-8 character without changing the encoding of earlier lines.
    text = ("中" * 87382).encode()
    split = _upload(api, student_a, ds, "split.txt", text)
    prefix = api(student_a).get(split["preview_url"]).json()
    assert prefix["truncated"] and prefix["content"] == "中" * 87381

    # 2) Image raw inline preview with nosniff + CSP sandbox
    png = _upload(api, student_a, ds, "scan.png", b"\x89PNG\r\n\x1a\nfake", "image/png")
    assert png["preview_kind"] == "image"
    raw_png = api(student_a).get(f"{png['preview_url']}?raw=1")
    assert raw_png.status_code == 200
    assert raw_png["Content-Type"] == "image/png"
    assert "inline" in raw_png["Content-Disposition"]
    assert raw_png["X-Content-Type-Options"] == "nosniff"
    assert "sandbox" in raw_png["Content-Security-Policy"]

    # 3) PDF raw inline preview
    pdf = _upload(api, student_a, ds, "report.pdf", b"%PDF-1.4\n%", "application/pdf")
    assert pdf["preview_kind"] == "pdf"
    raw_pdf = api(student_a).get(f"{pdf['preview_url']}?raw=1")
    assert raw_pdf.status_code == 200 and raw_pdf["Content-Type"] == "application/pdf"
    assert "inline" in raw_pdf["Content-Disposition"]

    # 4) SVG and HTML must NEVER be previewed inline (stored XSS protection)
    for danger_name, payload in (("evil.svg", b"<svg onload=alert(1)/>"), ("evil.html", b"<script>alert(1)</script>")):
        item = _upload(api, student_a, ds, danger_name, payload)
        assert item["preview_kind"] == "other"
        assert api(student_a).get(item["preview_url"]).json()["kind"] == "other"
        assert api(student_a).get(f"{item['preview_url']}?raw=1").status_code == 415

    # 5) Missing stored file returns 404 instead of 500
    missing = DataFile.objects.create(dataset=ds, name="gone.csv", file="datasets/missing.csv", size=10, sha256="0" * 64, uploaded_by=student_a)
    assert api(student_a).get(f"/api/files/{missing.pk}/preview/").status_code == 404
