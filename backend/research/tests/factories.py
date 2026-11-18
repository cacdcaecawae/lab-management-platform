"""ORM helpers for research tests (datasets are created directly, not through Agent C's API)."""

import datetime

from datasets.models import Dataset
from research.models import Experiment, ProcessingRun


def make_dataset(owner, project, kind=Dataset.Kind.RAW, name="数据"):
    return Dataset.objects.create(owner=owner, project=project, kind=kind, name=name)


def make_experiment(owner, project, **extra):
    extra.setdefault("title", "螺栓预紧力 A 组")
    extra.setdefault("date", datetime.date(2026, 11, 16))
    return Experiment.objects.create(owner=owner, project=project, **extra)


def make_run(owner, project, **extra):
    """A run that passes the reproducibility check on submit."""
    extra.setdefault("title", "导波包络提取")
    extra.setdefault("script_repo", "https://git.example.com/lab/guided-wave.git")
    extra.setdefault("script_commit", "a1b2c3d")
    extra.setdefault("environment", "Python 3.12, numpy 2.1")
    extra.setdefault("output_dataset", make_dataset(owner, project, Dataset.Kind.RESULT, "结果"))
    run = ProcessingRun.objects.create(owner=owner, project=project, **extra)
    run.inputs.add(make_dataset(owner, project, name="输入"))
    return run
