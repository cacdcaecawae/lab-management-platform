"""Dataset version codes, git style.

A version code is the SHA256 of the dataset's file list: one line "<file sha256>  <file name>" per file,
sorted by file name. It depends only on which files the dataset holds, not on upload order, so the same
files always give the same code. Files are never changed, so a dataset moves to a new version by gaining
files, or by its owner deleting a file that no submitted record holds (see held_versions()).

When a record (experiment, processing run, weekly report) is submitted it stores {dataset id: version code}
for every dataset it cites, and a DatasetSnapshot keeps that version's exact file list.
"""

import hashlib
from collections import defaultdict

from django.apps import apps

from .models import DataFile, Dataset, DatasetSnapshot

# The records that pin versions on submit, named rather than imported (they sit above datasets). Their pins hold while
# the record is not a draft: a returned record clears its pins and pins again on its next submit.
PIN_HOLDERS = (("research", "Experiment"), ("research", "ProcessingRun"), ("reports", "WeeklyReport"))


def digest_of(files):
    """files: (name, sha256) pairs in any order."""
    h = hashlib.sha256()
    for name, sha256 in sorted(files):
        h.update(f"{sha256}  {name}\n".encode())
    return h.hexdigest()


def current_version(dataset):
    return digest_of((f.name, f.sha256) for f in dataset.files.all())  # .all() reuses a prefetched file list


def current_versions(dataset_ids):
    """{dataset id: current version code}, in one query."""
    files = defaultdict(list)
    rows = DataFile.objects.filter(dataset_id__in=dataset_ids).values_list("dataset_id", "name", "sha256")
    for dataset_id, name, sha256 in rows:
        files[dataset_id].append((name, sha256))
    return {pk: digest_of(files[pk]) for pk in dataset_ids}


def lock_datasets(dataset_ids):
    """Row locks that order a submit's pinning against a file deletion in the same datasets (held until commit).
    NO KEY UPDATE: uploads, which only reference the row, still go on meanwhile."""
    list(Dataset.objects.select_for_update(no_key=True).filter(pk__in=dataset_ids).order_by("pk").values_list("pk"))


def pin_versions(datasets):
    """Snapshot each dataset as it is now; returns {dataset id (str, a JSON key): version code}."""
    lock_datasets([dataset.pk for dataset in datasets])
    pins = {}
    for dataset in datasets:
        # One read: the code and the stored file list come from the same rows even if an upload is running.
        files = list(DataFile.objects.filter(dataset=dataset))
        digest = digest_of((f.name, f.sha256) for f in files)
        snapshot, created = DatasetSnapshot.objects.get_or_create(dataset=dataset, digest=digest)
        if created:
            snapshot.files.set(files)
        pins[str(dataset.pk)] = digest
    return pins


def held_versions(dataset_id):
    """The version codes of this dataset that a submitted record pins."""
    key = str(dataset_id)
    held = set()
    for app_label, model_name in PIN_HOLDERS:
        holders = apps.get_model(app_label, model_name).objects.exclude(status="draft").filter(data_versions__has_key=key)
        held.update(pins[key] for pins in holders.values_list("data_versions", flat=True))
    return held


def locked_file_ids(dataset_id):
    """Files in a version a submitted record pins: they can no longer be deleted."""
    snapshots = DatasetSnapshot.objects.filter(dataset_id=dataset_id, digest__in=held_versions(dataset_id))
    return set(DataFile.objects.filter(dataset_id=dataset_id, snapshots__in=snapshots).values_list("pk", flat=True))


def add_pinned_versions(data, record, fields):
    """Datasets embedded in `fields` get "version" (the code pinned when the record was submitted; None for
    drafts and records submitted before versions existed) and "changed" (files were added since).
    A field may be (name, key): the embedded objects carry their dataset's id under `key` (a cited experiment's
    "dataset_id").
    shortcut: one query per submitted record, so list pages pay one query per row; fine at page size 20."""
    pins = record.data_versions or {}
    current = current_versions([int(pk) for pk in pins]) if pins else {}
    for field in fields:
        field, key = field if isinstance(field, tuple) else (field, "id")
        value = data.get(field)
        for item in value if isinstance(value, list) else [value] if value else []:
            pinned = pins.get(str(item[key]))
            item["version"] = pinned
            item["changed"] = pinned is not None and current.get(item[key]) != pinned
    return data
