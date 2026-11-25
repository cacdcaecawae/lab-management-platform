"""research/migrations/0007: records get their own files and nothing that existed stops showing up."""

import datetime
import importlib

import pytest
from django.apps import apps

from datasets.models import Dataset
from reports.models import WeeklyReport
from research.models import Experiment, ProcessingRun

pytestmark = pytest.mark.django_db
forwards = importlib.import_module("research.migrations.0007_records_own_files_data").forwards


def dataset(owner, project, kind="raw", name="数据", description=""):
    return Dataset.objects.create(owner=owner, project=project, kind=kind, name=name, description=description)


def experiment(owner, project, *linked, title="实验"):
    record = Experiment.objects.create(owner=owner, project=project, title=title, date=datetime.date(2026, 11, 16))
    record.datasets.add(*linked)
    return record


def upgraded(record):
    return type(record).objects.get(pk=record.pk)


def test_upgrade(student_a, project):
    alone = dataset(student_a, project, name="A 组波形")
    single = experiment(student_a, project, alone, title="单一数据")
    d1, d2 = dataset(student_a, project, name="d1"), dataset(student_a, project, name="d2")
    multi = experiment(student_a, project, d1, d2, title="两份数据")
    shared = dataset(student_a, project, name="两条记录共用")
    e1, e2 = experiment(student_a, project, shared), experiment(student_a, project, shared)
    standalone = dataset(student_a, project, name="单独登记的波形", description="示波器导出")
    unused_script = dataset(student_a, project, "script", "没用上的脚本")
    unused_result = dataset(student_a, project, "result", "没用上的结果", "峰值表")
    reported_script = dataset(student_a, project, "script", "周报里的脚本")
    WeeklyReport.objects.create(owner=student_a, week_start=datetime.date(2026, 11, 16)).datasets.add(reported_script)
    run = ProcessingRun.objects.create(
        owner=student_a, project=project, title="包络", script_repo="x", script_commit="y",
        status="submitted", data_versions={str(standalone.pk): "pinned"},
    )
    run.inputs.add(standalone, d1)

    forwards(apps, None)

    # an experiment keeps the one dataset it alone linked as its own raw data
    assert upgraded(single).dataset == alone and not single.datasets.exists()
    # otherwise it gets an empty one and keeps its links
    assert upgraded(multi).dataset.name == "两份数据" and not upgraded(multi).dataset.files.exists()
    assert set(multi.datasets.all()) == {d1, d2}
    for record in (e1, e2):
        assert upgraded(record).dataset not in (None, shared) and list(record.datasets.all()) == [shared]
    # a dataset no experiment showed is a draft experiment of its own
    wrapper = Experiment.objects.get(dataset=standalone)
    assert (wrapper.title, wrapper.steps, wrapper.status, wrapper.created_at) == ("单独登记的波形", "示波器导出", "draft", standalone.created_at)
    assert wrapper.history.filter(history_change_reason=f"升级：由早期数据集 DS-{standalone.created_at:%Y}-{standalone.pk:04d} 生成").exists()
    # the run cites that experiment instead; an input that is no experiment's own data stays an input
    run = upgraded(run)
    assert list(run.experiments.all()) == [wrapper] and list(run.inputs.all()) == [d1]
    assert run.script_dataset.kind == "script" and run.output_dataset.kind == "result"
    assert run.data_versions == {str(standalone.pk): "pinned"}  # still the cited experiment's raw data
    assert run.history.latest().history_change_reason == "升级：记录自带文件" and run.history.latest().history_user is None
    # a script or result dataset no record showed is a draft run of its own; one a weekly report shows stays as it is
    script_run = ProcessingRun.objects.get(script_dataset=unused_script)
    assert script_run.title == "没用上的脚本" and script_run.output_dataset.kind == "result"
    assert ProcessingRun.objects.get(output_dataset=unused_result).conclusion == "峰值表"
    assert not ProcessingRun.objects.filter(script_dataset=reported_script).exists()

    counts = (Experiment.objects.count(), ProcessingRun.objects.count(), Dataset.objects.count())
    forwards(apps, None)
    assert (Experiment.objects.count(), ProcessingRun.objects.count(), Dataset.objects.count()) == counts
