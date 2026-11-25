"""A dropped acquisition folder: each file is uploaded with its path inside the folder, which becomes its name."""

import io
import zipfile

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from datasets.models import DataFile

pytestmark = pytest.mark.django_db


def put(client, dataset, path, content=b"t,amp\n", name="data.csv"):
    data = {"file": SimpleUploadedFile(name, content), "path": path}
    return client.post(f"/api/datasets/{dataset.pk}/files/", data, format="multipart")


def test_the_same_file_name_in_two_subfolders(api, student_a, dataset_a):
    client = api(student_a)
    assert put(client, dataset_a, "采集/ch1/data.csv", b"1").json()[0]["name"] == "采集/ch1/data.csv"
    assert put(client, dataset_a, "采集\\ch2\\data.csv", b"2").status_code == 201  # Windows separators too
    response = put(client, dataset_a, "采集/ch1/data.csv", b"3")
    assert response.status_code == 409 and response.json()["code"] == "file_exists"

    archive = zipfile.ZipFile(io.BytesIO(b"".join(client.get(f"/api/datasets/{dataset_a.pk}/download-zip/").streaming_content)))
    assert sorted(archive.namelist()) == ["采集/ch1/data.csv", "采集/ch2/data.csv"]
    assert archive.read("采集/ch2/data.csv") == b"2"

    one = DataFile.objects.get(name="采集/ch1/data.csv")
    assert "data.csv" in client.get(f"/api/files/{one.pk}/download/")["Content-Disposition"]


def test_a_path_never_leaves_the_folder(api, student_a, dataset_a):
    client = api(student_a)
    assert put(client, dataset_a, "../../etc/./passwd").json()[0]["name"] == "etc/passwd"
    for path in ("..", "/./", "a/\x00/b", "x/" * 130):
        response = put(client, dataset_a, path)
        assert response.status_code == 400, path
        assert "file" in response.json()["errors"]


def test_a_path_names_one_file(api, student_a, dataset_a):
    data = {"file": [SimpleUploadedFile("a.csv", b"a"), SimpleUploadedFile("b.csv", b"b")], "path": "x/a.csv"}
    response = api(student_a).post(f"/api/datasets/{dataset_a.pk}/files/", data, format="multipart")
    assert response.status_code == 400 and "path" in response.json()["errors"]
