"""List filters shared by the modules: search that also finds a record by its code, sorting by a column, and the
plain "this column equals" filters."""

import re
from datetime import UTC, datetime

from django.db.models import Q
from rest_framework.filters import OrderingFilter, SearchFilter

from .params import plain_int

CODE = re.compile(r"([A-Z]+)-(\d{4})-(\d{1,18})")


def code_lookup(text, prefix):
    """The row a record code such as `EX-2026-0012` names, as a Q, or None when `text` is not a code with this prefix.
    A code is `<prefix>-<year created, UTC>-<id>` (the models' `code` property); it is not stored."""
    match = CODE.fullmatch(text.strip().upper())
    if not match or match[1] != prefix or not 2000 <= int(match[2]) <= 2999:
        return None
    start = datetime(int(match[2]), 1, 1, tzinfo=UTC)
    return Q(pk=int(match[3]), created_at__gte=start, created_at__lt=start.replace(year=start.year + 1))


class Search(SearchFilter):
    """DRF's search; a record code (the view's `code_prefix`) finds just that record."""

    def filter_queryset(self, request, queryset, view):
        prefix = getattr(view, "code_prefix", None)
        found = code_lookup(request.query_params.get(self.search_param, ""), prefix) if prefix else None
        return queryset.filter(found) if found is not None else super().filter_queryset(request, queryset, view)


class Ordering(OrderingFilter):
    """`?ordering=` by a column the view lists in `ordering_fields` (others are ignored); ties keep a fixed order by id,
    so pages do not overlap."""

    def get_ordering(self, request, queryset, view):
        ordering = super().get_ordering(request, queryset, view)
        return [*ordering, "-pk"] if ordering else ordering


def equal(queryset, params, **lookups):
    """`?<param>=<value>` as `<lookup>=<value>` for each given param. Text is compared as is; a lookup ending in `_id`
    takes an id. A value that cannot match (not an id, or holding NUL, which PostgreSQL cannot compare) gives no
    rows, as an unknown choice does elsewhere."""
    for param, lookup in lookups.items():
        value = params.get(param, "")
        if not value:
            continue
        if lookup.endswith("_id"):
            value = plain_int(value)
        if value is None or "\x00" in str(value):
            return queryset.none()
        queryset = queryset.filter(**{lookup: value})
    return queryset
