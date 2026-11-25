"""Who sees a dataset and its files: the owner and the group's advisors (core.permissions.scope_private), plus the
current members of a project whose submitted experiment or processing run holds the dataset (as
core.permissions.scope_research does for the records themselves)."""

from django.db.models import Q

from core.permissions import SUBMITTED, member, private_q, project_member_q

from .models import Dataset

# Reverse relations from a dataset to the records holding it, named rather than imported (research sits above): an
# experiment's own raw data and the datasets it linked earlier; a run's script and result files and its earlier inputs.
HOLDERS = ("raw_of", "experiments", "script_of_runs", "produced_by_runs", "used_by_runs")


def shared_dataset_ids(user):
    """Subqueries of the datasets held by a record shared with the user, one per kind of holder."""
    return [
        Dataset.objects.filter(project_member_q(user, f"{holder}__project"), **{f"{holder}__status": SUBMITTED}).values("pk")
        for holder in HOLDERS
    ]


def scope_datasets(queryset, user, owner_field="owner", dataset_field="pk"):
    """Datasets (owner_field="owner") or their files (owner_field="dataset__owner", dataset_field="dataset_id")."""
    if not member(user):
        return queryset.none()
    visible = private_q(user, owner_field)
    for ids in shared_dataset_ids(user):
        visible |= Q(**{f"{dataset_field}__in": ids})
    return queryset.filter(visible)
