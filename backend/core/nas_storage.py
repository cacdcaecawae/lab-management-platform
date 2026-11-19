"""Optional dedicated NAS storage. Never create a fallback files tree."""
from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from rest_framework.exceptions import APIException

MARKER = ".lab-storage-id"


class StorageUnavailable(APIException):
    status_code = 503
    default_detail = "主存储暂不可用，请稍后重试或联系运维"
    default_code = "storage_unavailable"


def nas_ready(root):
    """Verify the mounted app directory from this process, not just from the host."""
    identity = settings.LAB_NAS_STORAGE_ID
    if not identity:
        return False
    try:
        directory = Path(root)
        marker = directory.parent / MARKER
        if directory.is_symlink() or marker.is_symlink():
            return False
        with marker.open("rb") as handle:
            return handle.read(129).rstrip(b"\n") == identity.encode("ascii") and directory.is_dir()
    except (OSError, UnicodeError):
        return False


class NasFileStorage(FileSystemStorage):
    def _on_nas(self, operation, *args, **kwargs):
        if not nas_ready(self.location):
            raise StorageUnavailable()
        try:
            return operation(*args, **kwargs)
        except FileNotFoundError:
            # Preserve missing-file semantics if the mount is still valid.
            if nas_ready(self.location):
                raise
            raise StorageUnavailable() from None
        except OSError:
            raise StorageUnavailable() from None

    def _open(self, name, mode="rb"):
        return self._on_nas(super()._open, name, mode)

    def _save(self, name, content):
        return self._on_nas(super()._save, name, content)

    def exists(self, name):
        return self._on_nas(super().exists, name)

    def delete(self, name):
        return self._on_nas(super().delete, name)

    def size(self, name):
        return self._on_nas(super().size, name)
