"""ORM helpers for research tests. Records come with their own files, as the API creates them."""

import datetime

from django.core.files.base import ContentFile

from datasets.models import DataFile, Dataset
from research.models import Experiment, ProcessingRun


def make_dataset(owner, project, kind=Dataset.Kind.RAW, name="数据"):
    return Dataset.objects.create(owner=owner, project=project, kind=kind, name=name)


def add_file(dataset, name="波形.csv", content=b"t,amp\n0,1\n"):
    """A stored file in the dataset (sha256 is not checked here)."""
    data_file = DataFile(dataset=dataset, name=name, size=len(content), sha256=f"{len(content):064x}", uploaded_by=dataset.owner)
    data_file.file.save(name, ContentFile(content), save=False)
    data_file.save()
    return data_file


def make_experiment(owner, project, **extra):
    extra.setdefault("title", "螺栓预紧力 A 组")
    extra.setdefault("date", datetime.date(2026, 11, 16))
    extra.setdefault("dataset", make_dataset(owner, project, name="原始数据"))
    return Experiment.objects.create(owner=owner, project=project, **extra)


def make_run(owner, project, **extra):
    """A run that passes the reproducibility check on submit: it cites an experiment, names a git commit and states a
    conclusion."""
    extra.setdefault("title", "导波包络提取")
    extra.setdefault("script_repo", "https://git.example.com/lab/guided-wave.git")
    extra.setdefault("script_commit", "a1b2c3d")
    extra.setdefault("environment", "Python 3.12, numpy 2.1")
    extra.setdefault("conclusion", "包络峰值随预紧力下降")
    extra.setdefault("script_dataset", make_dataset(owner, project, Dataset.Kind.SCRIPT, "脚本"))
    extra.setdefault("output_dataset", make_dataset(owner, project, Dataset.Kind.RESULT, "结果"))
    run = ProcessingRun.objects.create(owner=owner, project=project, **extra)
    run.experiments.add(make_experiment(owner, project, title="输入"))
    return run
