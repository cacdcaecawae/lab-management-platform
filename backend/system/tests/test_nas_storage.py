import hashlib
from pathlib import Path

import pytest
from django.core.files.base import ContentFile
from django.core.management import call_command
from rest_framework.test import APIClient

from core.nas_storage import MARKER, NasFileStorage, StorageUnavailable

URL = "/api/system/storage-status/"
IDENTITY = "isolated-synthetic-test"


def storage(client):
    data = client.get(URL).json()
    return data["primary"], data["nas_ready"]


def mount(settings, tmp_path):
    root = tmp_path / "dedicated" / "files"
    root.mkdir(parents=True)
    settings.MEDIA_ROOT = root
    settings.LAB_NAS_STORAGE_ID = IDENTITY
    marker = root.parent / MARKER
    marker.write_bytes(IDENTITY.encode("ascii") + b"\n")
    return root, marker


def test_nas_io_and_missing_mount(settings, tmp_path):
    root, marker = mount(settings, tmp_path)
    storage = NasFileStorage()
    payload = b"t_us,amplitude\n0,3\n"
    name = storage.save("datasets/1/wave.csv", ContentFile(payload))
    with storage.open(name) as handle:
        assert hashlib.file_digest(handle, "sha256").digest() == hashlib.sha256(payload).digest()
    assert storage.size(name) == len(payload)
    with pytest.raises(FileNotFoundError):
        storage.open("missing")
    marker.write_text("wrong storage\n")
    with pytest.raises(StorageUnavailable):
        storage.save("datasets/1/wrong.csv", ContentFile(payload))
    with pytest.raises(StorageUnavailable):
        storage.delete(name)
    assert not (root / "datasets/1/wrong.csv").exists()
    assert (root / name).read_bytes() == payload


def test_absent_directory_is_not_created(settings, tmp_path):
    settings.LAB_NAS_STORAGE_ID = IDENTITY
    root = tmp_path / "unmounted" / "files"
    settings.MEDIA_ROOT = root
    with pytest.raises(StorageUnavailable):
        NasFileStorage().save("wave.csv", ContentFile(b"test"))
    assert not root.exists()


@pytest.mark.django_db
def test_status_is_read_only_and_restricted(settings, tmp_path, api, ops, manager):
    client = api(ops)
    assert storage(client) == ("local", None)
    assert client.post(URL, {"primary": "nas"}, format="json").status_code == 405
    assert api(manager).get(URL).status_code == 403
    assert APIClient().get(URL).status_code in (401, 403)
    root, marker = mount(settings, tmp_path)
    call_command("record_ops_run", "backup", "ok")
    assert storage(client) == ("nas", True)
    assert client.get(URL).json()["attention"] is False
    marker.unlink()
    marker.symlink_to(tmp_path / "not-the-nas")
    assert storage(client) == ("nas", False)
    assert client.get(URL).json()["attention"] is True  # file operations are paused
    assert list(Path(root).iterdir()) == []
