import hashlib
from urllib.parse import quote

import pytest

from datasets import views
from datasets.models import DataFile
from datasets.views import clean_file_name

pytestmark = pytest.mark.django_db


def raw_upload(client, dataset, filename, content=b"x"):
    """POST a hand-built multipart body; the test client would basename() the filename itself."""
    boundary = "testboundary"
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
    return client.post(
        f"/api/datasets/{dataset.pk}/files/", body, content_type=f"multipart/form-data; boundary={boundary}"
    )


def download(client, file_id):
    resp = client.get(f"/api/files/{file_id}/download/")
    # Draining streaming_content also closes the file: the test client wraps it like a WSGI server.
    content = b"".join(resp.streaming_content) if resp.streaming else None
    return resp, content


def test_upload_single_file(api, student_a, dataset_a, upload, stored_files):
    content = b"\x00\x01waveform" * 1000
    resp = upload(api(student_a), dataset_a, [("波形1.csv", content)])
    assert resp.status_code == 201
    [body] = resp.json()
    f = DataFile.objects.get()
    assert body == {
        "id": f.pk, "dataset_id": dataset_a.pk, "name": "波形1.csv", "size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(), "uploaded_by": {"id": student_a.pk, "name": student_a.name},
        "uploaded_at": body["uploaded_at"], "download_url": f"/api/files/{f.pk}/download/",
    }
    [path] = stored_files()
    assert path.read_bytes() == content
    assert f.file.name.startswith(f"datasets/{dataset_a.pk}/") and "波形" not in f.file.name


def test_upload_multiple_files(api, student_a, dataset_a, upload, stored_files):
    files = [("a.bin", b"alpha"), ("b.bin", b"bravo" * 100)]
    resp = upload(api(student_a), dataset_a, files)
    assert resp.status_code == 201
    assert [(d["name"], d["sha256"]) for d in resp.json()] == [(n, hashlib.sha256(c).hexdigest()) for n, c in files]
    assert sorted(p.read_bytes() for p in stored_files()) == sorted(c for _, c in files)


def test_upload_spooled_to_temp_file(api, student_a, dataset_a, upload, stored_files, settings):
    settings.FILE_UPLOAD_MAX_MEMORY_SIZE = 1024  # force TemporaryUploadedFile, as real large uploads get
    content = bytes(range(256)) * 400
    [body] = upload(api(student_a), dataset_a, [("big.bin", content)]).json()
    assert body["sha256"] == hashlib.sha256(content).hexdigest() and body["size"] == len(content)
    [path] = stored_files()
    assert path.read_bytes() == content


def test_upload_without_file_is_400(api, student_a, dataset_a):
    resp = api(student_a).post(f"/api/datasets/{dataset_a.pk}/files/", {}, format="multipart")
    assert resp.status_code == 400
    assert "file" in resp.json()["errors"]


def test_client_sha256_match_is_accepted(api, student_a, dataset_a, upload):
    content = b"payload"
    resp = upload(api(student_a), dataset_a, [("a.bin", content)], sha256=hashlib.sha256(content).hexdigest().upper())
    assert resp.status_code == 201


def test_client_sha256_mismatch_is_400_and_nothing_saved(api, student_a, dataset_a, upload, stored_files):
    resp = upload(api(student_a), dataset_a, [("a.bin", b"payload")], sha256=hashlib.sha256(b"other").hexdigest())
    assert resp.status_code == 400
    assert "sha256" in resp.json()["errors"]
    assert not DataFile.objects.exists() and stored_files() == []


def test_client_sha256_with_several_files_is_400(api, student_a, dataset_a, upload, stored_files):
    resp = upload(api(student_a), dataset_a, [("a", b"a"), ("b", b"b")], sha256=hashlib.sha256(b"a").hexdigest())
    assert resp.status_code == 400
    assert "sha256" in resp.json()["errors"]
    assert stored_files() == []


def test_same_name_is_409_and_original_untouched(api, student_a, dataset_a, upload, stored_files):
    client = api(student_a)
    upload(client, dataset_a, [("a.bin", b"original")])
    before = stored_files()
    resp = upload(client, dataset_a, [("a.bin", b"replacement")])
    assert resp.status_code == 409
    assert resp.json()["code"] == "file_exists"
    assert stored_files() == before and before[0].read_bytes() == b"original"
    assert DataFile.objects.get().sha256 == hashlib.sha256(b"original").hexdigest()


def test_duplicate_within_request_saves_nothing(api, student_a, dataset_a, upload, stored_files):
    resp = upload(api(student_a), dataset_a, [("a.bin", b"1"), ("c.bin", b"3"), ("a.bin", b"2")])
    assert resp.status_code == 409
    assert resp.json()["code"] == "file_exists"
    assert not DataFile.objects.exists() and stored_files() == []


def test_one_existing_name_in_batch_saves_nothing(api, student_a, dataset_a, upload, stored_files):
    client = api(student_a)
    upload(client, dataset_a, [("a.bin", b"1")])
    resp = upload(client, dataset_a, [("new.bin", b"2"), ("a.bin", b"3")])
    assert resp.status_code == 409
    assert list(DataFile.objects.values_list("name", flat=True)) == ["a.bin"]
    assert len(stored_files()) == 1


def test_same_name_in_another_dataset_is_fine(api, student_a, dataset_a, project, upload):
    from datasets.models import Dataset

    other = Dataset.objects.create(owner=student_a, project=project, name="另一批")
    client = api(student_a)
    assert upload(client, dataset_a, [("a.bin", b"1")]).status_code == 201
    assert upload(client, other, [("a.bin", b"2")]).status_code == 201


def test_too_large_is_413(api, student_a, dataset_a, upload, stored_files, settings):
    settings.MAX_UPLOAD_SIZE = 10
    resp = upload(api(student_a), dataset_a, [("small.bin", b"0123456789"), ("big.bin", b"01234567890")])
    assert resp.status_code == 413
    assert resp.json()["code"] == "file_too_large"
    assert not DataFile.objects.exists() and stored_files() == []


@pytest.mark.parametrize(("sent", "saved"), [("../../etc/passwd", "passwd"), ("a\\b.txt", "b.txt"), ("  中文 名.txt ", "中文 名.txt")])
def test_path_like_names_keep_only_basename(api, student_a, dataset_a, stored_files, settings, sent, saved):
    resp = raw_upload(api(student_a), dataset_a, sent, b"secret")
    assert resp.status_code == 201
    assert resp.json()[0]["name"] == saved
    f = DataFile.objects.get()
    assert f.file.name.startswith(f"datasets/{dataset_a.pk}/") and saved not in f.file.name
    [path] = stored_files()
    assert path.relative_to(settings.MEDIA_ROOT).as_posix() == f.file.name


def test_overlong_name_is_cut_to_column_length(api, student_a, dataset_a):
    resp = raw_upload(api(student_a), dataset_a, "长" * 300 + ".csv")
    assert resp.status_code == 201
    name = resp.json()[0]["name"]
    assert len(name) == 255 and name.endswith(".csv")


@pytest.mark.parametrize("sent", ["   ", "dir/ ", "a\\.."])
def test_unusable_names_are_400(api, student_a, dataset_a, stored_files, sent):
    resp = raw_upload(api(student_a), dataset_a, sent)
    assert resp.status_code == 400
    assert not DataFile.objects.exists() and stored_files() == []


@pytest.mark.parametrize(
    ("raw", "cleaned"),
    [
        ("data.csv", "data.csv"),
        ("../../etc/passwd", "passwd"),
        ("C:\\Users\\x\\a b.txt", "a b.txt"),
        ("dir/sub\\file.bin", "file.bin"),
        ("  name.txt  ", "name.txt"),
        ("..", ""),
        ("a/.", ""),
        ("x\\ ", ""),
        ("", ""),
    ],
)
def test_clean_file_name(raw, cleaned):
    assert clean_file_name(raw) == cleaned


def test_concurrent_same_name_is_409_without_orphan(api, student_a, dataset_a, upload, stored_files, monkeypatch):
    real_sha256_of = views.sha256_of

    def racing_sha256_of(uploaded):
        # Another request commits the same name after our duplicate check passed.
        DataFile.objects.create(dataset=dataset_a, name="race.bin", file="datasets/x/y", size=1, sha256="0" * 64, uploaded_by=student_a)
        return real_sha256_of(uploaded)

    monkeypatch.setattr(views, "sha256_of", racing_sha256_of)
    resp = upload(api(student_a), dataset_a, [("race.bin", b"mine")])
    assert resp.status_code == 409
    assert resp.json()["code"] == "file_exists"
    assert stored_files() == []


def test_unexpected_error_mid_batch_removes_written_files(api, student_a, dataset_a, upload, stored_files, monkeypatch):
    real_save = DataFile.save
    saved = []

    def failing_second_save(self, *args, **kwargs):
        saved.append(self.name)
        if len(saved) == 2:
            raise RuntimeError("disk on fire")
        return real_save(self, *args, **kwargs)

    monkeypatch.setattr(DataFile, "save", failing_second_save)
    with pytest.raises(RuntimeError):
        upload(api(student_a), dataset_a, [("a.bin", b"1"), ("b.bin", b"2")])
    assert not DataFile.objects.exists() and stored_files() == []


def test_file_list_is_sorted_and_not_paginated(api, student_a, dataset_a, upload):
    client = api(student_a)
    upload(client, dataset_a, [("c.bin", b"c"), ("a.bin", b"a"), ("b.bin", b"b")])
    resp = client.get(f"/api/datasets/{dataset_a.pk}/files/")
    assert resp.status_code == 200
    assert [f["name"] for f in resp.json()] == ["a.bin", "b.bin", "c.bin"]


def test_file_detail_and_download(api, student_a, dataset_a, upload):
    client = api(student_a)
    content = "超声,幅值\n1,0.5\n".encode()
    [meta] = upload(client, dataset_a, [("实验数据 v1.csv", content)]).json()
    assert client.get(f"/api/files/{meta['id']}/").json() == meta
    resp, body = download(client, meta["id"])
    assert resp.status_code == 200 and body == content
    disposition = resp["Content-Disposition"]
    assert disposition.startswith("attachment") and quote("实验数据 v1.csv") in disposition


def test_files_endpoint_has_no_list_update_or_delete(api, student_a, dataset_a, upload):
    client = api(student_a)
    [meta] = upload(client, dataset_a, [("a.bin", b"1")]).json()
    assert client.get("/api/files/").status_code == 404
    assert client.patch(f"/api/files/{meta['id']}/", {"name": "b"}, format="json").status_code == 405
    assert client.delete(f"/api/files/{meta['id']}/").status_code == 405
    assert DataFile.objects.get().name == "a.bin"


def test_isolation_between_students(api, student_a, student_b, dataset_b, upload, stored_files):
    [meta] = upload(api(student_b), dataset_b, [("b.bin", b"private")]).json()
    client = api(student_a)
    assert client.get(f"/api/datasets/{dataset_b.pk}/files/").status_code == 404
    assert upload(client, dataset_b, [("x.bin", b"x")]).status_code == 404
    assert client.get(f"/api/files/{meta['id']}/").status_code == 404
    assert download(client, meta["id"])[0].status_code == 404
    assert len(stored_files()) == 1


def test_other_group_manager_gets_404(api, student_a, other_manager, dataset_a, upload):
    [meta] = upload(api(student_a), dataset_a, [("a.bin", b"private")]).json()
    client = api(other_manager)
    assert client.get(f"/api/datasets/{dataset_a.pk}/files/").status_code == 404
    assert upload(client, dataset_a, [("x.bin", b"x")]).status_code == 404
    assert client.get(f"/api/files/{meta['id']}/").status_code == 404
    assert download(client, meta["id"])[0].status_code == 404


def test_supervisors_read_and_download_but_cannot_upload(api, student_a, manager, advisor, dataset_a, upload, stored_files):
    [meta] = upload(api(student_a), dataset_a, [("a.bin", b"private")]).json()
    for user in (manager, advisor):
        client = api(user)
        assert client.get(f"/api/datasets/{dataset_a.pk}/files/").status_code == 200
        assert client.get(f"/api/files/{meta['id']}/").status_code == 200
        resp, body = download(client, meta["id"])
        assert resp.status_code == 200 and body == b"private"
        resp = upload(client, dataset_a, [("x.bin", b"x")])
        assert resp.status_code == 403
        assert resp.json()["code"] == "permission_denied"
    assert DataFile.objects.count() == 1 and len(stored_files()) == 1


def test_anonymous_is_rejected(api, dataset_a):
    assert api().get(f"/api/datasets/{dataset_a.pk}/files/").status_code == 403
