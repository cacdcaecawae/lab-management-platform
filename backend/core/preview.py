"""Safe online preview helpers for stored files (images, PDFs, and capped UTF-8/GB18030 text/CSV).

SVG, HTML, XML and scripts are never served inline here so uploaded files cannot execute in this origin.
"""

import codecs
from pathlib import Path

from django.http import FileResponse
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound
from rest_framework.response import Response

IMAGE_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}
PDF_MIME = {".pdf": "application/pdf"}
TEXT_EXTS = {
    ".csv", ".tsv", ".txt", ".md", ".json", ".yaml", ".yml", ".log",
    ".py", ".m", ".c", ".h", ".cpp", ".ini", ".toml",
}
MAX_PREVIEW_BYTES = 256 * 1024
MAX_PREVIEW_LINES = 200


class UnsupportedPreview(APIException):
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    default_detail = "该文件类型不支持在线预览，请下载查看"
    default_code = "unsupported_preview"


def preview_kind(name: str) -> str:
    ext = Path(name or "").suffix.lower()
    if ext in IMAGE_MIME:
        return "image"
    if ext in PDF_MIME:
        return "pdf"
    if ext in TEXT_EXTS:
        return "text"
    return "other"


def _decode_text(raw: bytes, truncated: bool) -> str:
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return codecs.getincrementaldecoder(encoding)().decode(raw, final=not truncated)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def read_text_preview(field_file, name: str, size=None, max_bytes=MAX_PREVIEW_BYTES, max_lines=MAX_PREVIEW_LINES):
    try:
        with field_file.open("rb") as fh:
            raw = fh.read(max_bytes + 1)
    except FileNotFoundError:
        raise NotFound() from None

    byte_truncated = len(raw) > max_bytes
    if byte_truncated:
        raw = raw[:max_bytes]
    text = _decode_text(raw, byte_truncated)
    all_lines = text.splitlines()
    # If truncated mid-line by the byte cap, drop the partial trailing line when multiple lines exist.
    if byte_truncated and len(all_lines) > 1:
        all_lines = all_lines[:-1]
    line_truncated = len(all_lines) > max_lines
    lines = all_lines[:max_lines]
    ext = Path(name or "").suffix.lower()
    fmt = "csv" if ext == ".csv" else "tsv" if ext == ".tsv" else "plain"
    return {
        "kind": "text",
        "format": fmt,
        "name": name,
        "size": size,
        "truncated": byte_truncated or line_truncated,
        "lines": len(lines),
        "content": "\n".join(lines),
    }


def preview_response(field_file, name: str, size=None, raw: bool = False):
    kind = preview_kind(name)
    ext = Path(name or "").suffix.lower()
    if raw:
        mime = IMAGE_MIME.get(ext) or PDF_MIME.get(ext)
        if not mime:
            raise UnsupportedPreview()
        try:
            fh = field_file.open("rb")
        except FileNotFoundError:
            raise NotFound() from None
        resp = FileResponse(fh, as_attachment=False, filename=name, content_type=mime)
        resp["Cache-Control"] = "private, no-store"
        resp["X-Content-Type-Options"] = "nosniff"
        if kind == "image":
            resp["Content-Security-Policy"] = "default-src 'none'; sandbox"
        else:
            resp["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'self'"
        return resp

    if kind == "text":
        resp = Response(read_text_preview(field_file, name, size=size))
        resp["Cache-Control"] = "private, no-store"
        return resp
    return Response({"kind": kind, "name": name, "size": size})
