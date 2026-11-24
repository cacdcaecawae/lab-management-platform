"""The site's file storage: Django's, except that a write failing halfway leaves nothing behind."""
from django.core.files.storage import FileSystemStorage


class CleanFileSystemStorage(FileSystemStorage):
    """A file whose write fails halfway (disk full, an I/O error, a temp file that cannot be moved) is removed again:
    no row will point at it, so nothing else would ever clean it up. Only a name that was free before is removed:
    when it was taken, Django writes under another name, and the file already there is someone else's."""

    def _save(self, name, content):
        fresh = not self.exists(name)
        try:
            return super()._save(name, content)
        except BaseException:
            if fresh:
                try:
                    self.delete(name)
                except Exception:  # the write's own error is the one to report
                    pass
            raise
