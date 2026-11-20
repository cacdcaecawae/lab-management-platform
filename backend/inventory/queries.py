"""Inventory aggregates shared by the list and workbench."""
from django.db.models import F, Prefetch, Sum

from .models import Batch


def batches_with_balance():
    return Batch.objects.annotate(stock=Sum("txns__quantity", default=0)).order_by(
        F("expires_on").asc(nulls_last=True), "pk"
    )


def batch_details():
    return Prefetch("batches", queryset=batches_with_balance(), to_attr="stock_batches")
