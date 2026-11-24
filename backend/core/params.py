"""Query-string values that reach the database."""

from django.utils.dateparse import parse_date
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


def day_param(params, name):
    """`params[name]` (YYYY-MM-DD) as a date, or None when it is not given; anything else is a 400."""
    text = params.get(name)
    if not text:
        return None
    try:
        day = parse_date(text)
    except ValueError:  # the right shape, not a date: 2026-13-45
        day = None
    if day is None:
        raise ValidationError({name: ["格式为 YYYY-MM-DD"]})
    return day
