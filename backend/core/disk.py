"""Free disk space where uploads land. Uploads are refused before they would fill the disk: a full disk also stops
PostgreSQL and the nightly backup (in the default install everything is on one disk)."""
import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.files.uploadhandler import FileUploadHandler

from .exceptions import InsufficientStorage


def free_bytes():
    """The smaller free space of the upload spool and the attachment store; None if neither can be read."""
    free = []
    for path in (Path(settings.FILE_UPLOAD_TEMP_DIR or tempfile.gettempdir()), Path(settings.MEDIA_ROOT)):
        while not path.exists() and path != path.parent:  # not created yet: the disk it will be on
            path = path.parent
        try:
            free.append(shutil.disk_usage(path).free)
        except OSError:
            pass
    return min(free, default=None)


class DiskSpaceGuard(FileUploadHandler):
    """First upload handler: refuses a body that would leave less than MIN_FREE_DISK, before any of it is spooled."""

    def handle_raw_input(self, input_data, META, content_length, boundary, encoding=None):
        free = free_bytes()
        if free is not None and free - content_length < settings.MIN_FREE_DISK:
            raise InsufficientStorage()

    def receive_data_chunk(self, raw_data, start):
        return raw_data  # the next handler stores it

    def file_complete(self, file_size):
        return None
