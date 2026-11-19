"""Stored uploads of the knowledge base, meetings and achievements: server-generated storage names, downloads that
cannot run in the browser, and file cleanup after the rows are gone."""

import hashlib
import uuid
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.http import FileResponse
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError


class FileTooLarge(APIException):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    default_detail = "文件超过大小上限"
    default_code = "file_too_large"


def clean_file_name(raw):
    """Last path component of a client-supplied name, for either separator; "" if unusable."""
    name = raw.replace("\\", "/").rsplit("/", 1)[-1].strip()
    return "" if name in (".", "..") else name


def sha256_of(uploaded):
    digest = hashlib.sha256()
    for chunk in uploaded.chunks():
        digest.update(chunk)
    return digest.hexdigest()


# Opened in the browser; anything else (HTML, SVG, scripts...) is sent as a download so it never runs on this site.
INLINE_TYPES = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp"}


def stored_name(folder, filename):
    """The client's file name never becomes a storage path; it is kept in the row's `name`."""
    return f"{folder}/{uuid.uuid4().hex}{Path(filename).suffix.lower()[:16]}"


def checked_upload(request, max_size=None, types=None):
    """(uploaded file, clean name) of the `file` field, or a 400 / 413."""
    uploaded = request.FILES.get("file")
    if not uploaded:
        raise ValidationError({"file": ["请选择要上传的文件"]})
    name = clean_file_name(uploaded.name or "")
    if not name:
        raise ValidationError({"file": [f"文件名无效：{uploaded.name!r}"]})
    if types and Path(name).suffix.lower() not in types:
        raise ValidationError({"file": [f"只支持 {'、'.join(sorted(t.lstrip('.').upper() for t in types))}"]})
    limit = max_size or settings.MAX_UPLOAD_SIZE
    if uploaded.size > limit:
        raise FileTooLarge(f"{name} 超过单个文件上限 {limit // 1024**2} MB")
    return uploaded, name


def download(field_file, name):
    inline = Path(name).suffix.lower() in INLINE_TYPES
    return FileResponse(field_file.open("rb"), as_attachment=not inline, filename=name)


def delete_on_commit(field_files):
    """Delete stored files once the transaction that removed or replaced their rows has committed."""
    for f in field_files:
        if f:
            delete_name_on_commit(f.storage, f.name)


def delete_name_on_commit(storage, name):
    # robust: the change is already saved, so a file that cannot go (locked, already gone) is logged and left
    # behind instead of turning the saved change into an error. One callback per file: one failure skips no other.
    # A lambda, not functools.partial: Django logs a failed robust callback by its __qualname__.
    transaction.on_commit(lambda: storage.delete(name), robust=True)
