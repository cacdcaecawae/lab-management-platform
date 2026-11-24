"""The site's file storage: Django's, except that a write failing halfway leaves nothing behind."""
from contextvars import ContextVar

from django.core.files.storage import FileSystemStorage

# The names one _save tried: Django moves on to a new name when the one it was given is taken at the moment it writes.
_tried = ContextVar("tried", default=None)


class CleanFileSystemStorage(FileSystemStorage):
    """A file whose write fails halfway (disk full, an I/O error, a temp file that cannot be moved) is removed again:
    no row will point at it, so nothing else would ever clean it up. Only the file this write made goes: the last name
    it tried, which it created itself (O_EXCL) or never got. A name taken meanwhile holds someone else's file."""

    def get_available_name(self, name, max_length=None):
        name = super().get_available_name(name, max_length=max_length)
        if (tried := _tried.get()) is not None:
            tried.append(name)
        return name

    def _save(self, name, content):
        tried = [name]
        token = _tried.set(tried)
        try:
            return super()._save(name, content)
        except BaseException:
            try:
                self.delete(tried[-1])
            except Exception:  # the write's own error is the one to report
                pass
            raise
        finally:
            _tried.reset(token)
