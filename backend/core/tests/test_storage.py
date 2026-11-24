"""A write failing halfway leaves no file behind (issue #48 B3)."""
import pytest
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import TemporaryUploadedFile

from core.storage import CleanFileSystemStorage


class Broken(ContentFile):
    """Its second chunk never arrives: a full disk, an I/O error."""

    def chunks(self, chunk_size=None):
        yield b"half written"
        raise OSError("No space left on device")


def test_a_write_failing_halfway_leaves_nothing(tmp_path):
    storage = CleanFileSystemStorage(location=tmp_path)
    with pytest.raises(OSError):
        storage.save("procurement/a.pdf", Broken(b""))
    assert not (tmp_path / "procurement" / "a.pdf").exists()
    assert storage.save("procurement/b.pdf", ContentFile(b"%PDF")) == "procurement/b.pdf"  # a whole write stays


def test_a_file_already_there_is_left_alone(tmp_path):
    storage = CleanFileSystemStorage(location=tmp_path)
    storage.save("x.pdf", ContentFile(b"someone else's"))
    with pytest.raises(OSError):
        storage.save("x.pdf", Broken(b""))  # Django writes under another name; that one fails
    assert (tmp_path / "x.pdf").read_bytes() == b"someone else's"


def test_a_name_taken_while_writing_keeps_that_file(tmp_path):
    """Two writes given one name: the first lands, the second moves to a new name and fails there. The first file
    stays, and the half-written second one goes."""
    storage = CleanFileSystemStorage(location=tmp_path)
    storage.save("x.pdf", ContentFile(b"the first write"))
    with pytest.raises(OSError):
        storage._save("x.pdf", Broken(b""))  # as if it had checked the name before the first write landed
    assert (tmp_path / "x.pdf").read_bytes() == b"the first write"
    assert [p.name for p in tmp_path.iterdir()] == ["x.pdf"]


def test_error_choosing_another_name_keeps_the_first_file(tmp_path, monkeypatch):
    storage = CleanFileSystemStorage(location=tmp_path)
    storage.save("x.pdf", ContentFile(b"first"))

    def unavailable(name):
        raise OSError("temporary I/O error")

    monkeypatch.setattr(storage, "get_available_name", unavailable)
    with pytest.raises(OSError, match="temporary I/O error"):
        storage._save("x.pdf", ContentFile(b"second"))
    assert (tmp_path / "x.pdf").read_bytes() == b"first"


def test_spooled_upload_uses_its_own_destination(tmp_path):
    storage = CleanFileSystemStorage(location=tmp_path)
    storage.save("x.pdf", ContentFile(b"first"))
    with TemporaryUploadedFile("x.pdf", "application/pdf", 6, None) as upload:
        upload.write(b"second")
        upload.seek(0)
        saved = storage._save("x.pdf", upload)
    assert (tmp_path / "x.pdf").read_bytes() == b"first"
    assert (tmp_path / saved).read_bytes() == b"second"
