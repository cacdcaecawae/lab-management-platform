"""A write failing halfway leaves no file behind (issue #48 B3)."""
import pytest
from django.core.files.base import ContentFile

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
