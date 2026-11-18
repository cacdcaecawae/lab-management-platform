"""Dataset version codes, git style.

A version code is the SHA256 of the dataset's file list: one line "<file sha256>  <file name>" per file,
sorted by file name. It depends only on which files the dataset holds, not on upload order, so the same
files always give the same code. Files are never changed or deleted, so a dataset only moves to a new
version by gaining files.

When a record (experiment, processing run, weekly report) is submitted it stores {dataset id: version code}
for every dataset it cites, and a DatasetSnapshot keeps that version's exact file list.
"""

import hashlib
from collections import defaultdict

from .models import DataFile, DatasetSnapshot


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


def pin_versions(datasets):
    """Snapshot each dataset as it is now; returns {dataset id (str, a JSON key): version code}."""
    pins = {}
    for dataset in datasets:
        # One read: the code and the stored file list come from the same rows even if an upload is running.
        files = list(dataset.files.all())
        digest = digest_of((f.name, f.sha256) for f in files)
        snapshot, created = DatasetSnapshot.objects.get_or_create(dataset=dataset, digest=digest)
        if created:
            snapshot.files.set(files)
        pins[str(dataset.pk)] = digest
    return pins


def add_pinned_versions(data, record, fields):
    """Datasets embedded in `fields` get "version" (the code pinned when the record was submitted; None for
    drafts and records submitted before versions existed) and "changed" (files were added since).
    shortcut: one query per submitted record, so list pages pay one query per row; fine at page size 20."""
    pins = record.data_versions or {}
    current = current_versions([int(pk) for pk in pins]) if pins else {}
    for field in fields:
        value = data.get(field)
        for dataset in value if isinstance(value, list) else [value] if value else []:
            pinned = pins.get(str(dataset["id"]))
            dataset["version"] = pinned
            dataset["changed"] = pinned is not None and current.get(dataset["id"]) != pinned
    return data
