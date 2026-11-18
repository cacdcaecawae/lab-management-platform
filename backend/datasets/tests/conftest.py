from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from datasets.models import Dataset


@pytest.fixture
def dataset_a(project, student_a):
    return Dataset.objects.create(owner=student_a, project=project, name="A 原始波形")


@pytest.fixture
def dataset_b(project, student_b):
    return Dataset.objects.create(owner=student_b, project=project, name="B 原始波形")


@pytest.fixture
def upload():
    """upload(client, dataset, [("name", b"content"), ...], **form) -> response"""

    def _upload(client, dataset, files, **form):
        data = {"file": [SimpleUploadedFile(name, content) for name, content in files], **form}
        return client.post(f"/api/datasets/{dataset.pk}/files/", data, format="multipart")

    return _upload


@pytest.fixture
def stored_files(settings):
    """Every file currently in MEDIA_ROOT (the per-test storage directory)."""

    def _stored_files():
        root = Path(settings.MEDIA_ROOT)
        return sorted(p for p in root.rglob("*") if p.is_file()) if root.exists() else []

    return _stored_files
