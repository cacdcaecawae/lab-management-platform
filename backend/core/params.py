"""Query-string values that reach the database."""

from rest_framework.exceptions import ValidationError


def plain_int(text, digits=18):
    """`text` as an int when it is a plain ASCII number that fits a bigint column, else None.
    ("²" and "١" pass str.isdigit() but not int(); 20 digits pass int() but not PostgreSQL.)"""
    return int(text) if text.isascii() and text.isdigit() and len(text) <= digits else None


def search_text(params):
    """The `search` value for a hand-written search; a NUL in it is a 400 as with DRF's SearchFilter (PostgreSQL cannot
    compare text holding one)."""
    keyword = params.get("search", "").strip()
    if "\x00" in keyword:
        raise ValidationError({"search": ["搜索词里有无效字符"]})
    return keyword
