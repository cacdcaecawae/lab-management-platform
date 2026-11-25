"""Filesystem storage for immutable uploads on the server or its NAS mount."""
import os
from contextlib import suppress

from django.core.files.move import file_move_safe
from django.core.files.storage import FileSystemStorage
from django.utils._os import safe_makedirs


class CleanFileSystemStorage(FileSystemStorage):
    def _save(self, name, content):
        directory = os.path.dirname(self.path(name))
        if self.directory_permissions_mode is None:
            os.makedirs(directory, exist_ok=True)
        else:
            safe_makedirs(directory, self.directory_permissions_mode, exist_ok=True)

        while True:
            path = self.path(name)
            try:
                target = open(path, "xb")
                break
            except FileExistsError:
                if self._allow_overwrite:
                    return super()._save(name, content)
                name = self.get_available_name(name)

        # Only a successful exclusive open gives this write a file to clean up.
        try:
            with target:
                if hasattr(content, "temporary_file_path"):
                    target.close()
                    file_move_safe(content.temporary_file_path(), path, allow_overwrite=True)
                else:
                    for chunk in content.chunks():
                        target.write(chunk.encode() if isinstance(chunk, str) else chunk)
            if self.file_permissions_mode is not None:
                os.chmod(path, self.file_permissions_mode)
            self._ensure_location_group_id(path)
        except BaseException:
            with suppress(Exception):  # preserve the write error if the disk or NAS is still unavailable
                self.delete(name)
            raise
        return name
