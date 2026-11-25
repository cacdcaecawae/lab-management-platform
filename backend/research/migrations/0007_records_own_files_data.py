"""Records hold their own files (issue #58 P1): every experiment gets its own raw data, every processing run its own
script and result files, and runs cite experiments instead of raw datasets.

Nothing is deleted and no stored file moves. A raw dataset that an experiment alone linked becomes that experiment's
own raw data; a dataset that no record would show any more becomes a draft record of its own (named after it), so it
stays findable in 实验与原始数据 and 数据处理. Pinned versions keep their dataset ids, so snapshots stay valid.
Every change is written to the records' history as 系统 with a reason, so it is not shown as someone's next edit.
"""

from django.db import migrations
from django.utils import timezone

RAW_KINDS = ("raw", "other")
REASON = "升级：记录自带文件"


def forwards(apps, schema_editor):
    Dataset = apps.get_model("datasets", "Dataset")
    Experiment = apps.get_model("research", "Experiment")
    ProcessingRun = apps.get_model("research", "ProcessingRun")
    history = {
        Experiment: apps.get_model("research", "HistoricalExperiment"),
        ProcessingRun: apps.get_model("research", "HistoricalProcessingRun"),
    }

    def remember(record, kind, reason, when=None):
        """A history row as of now, by no user (shown as 系统)."""
        record.refresh_from_db()
        values = {field.attname: getattr(record, field.attname) for field in record._meta.concrete_fields}
        history[type(record)].objects.create(
            **values, history_type=kind, history_date=when or timezone.now(), history_change_reason=reason, history_user=None
        )

    def files_for(owner_id, project_id, name, kind):
        return Dataset.objects.create(owner_id=owner_id, project_id=project_id, name=name[:200], kind=kind)

    def code(dataset):
        return f"DS-{dataset.created_at:%Y}-{dataset.pk:04d}"

    # 1. An experiment keeps, as its own raw data, the one raw dataset of its owner that it alone linked; else it gets
    #    an empty one. Its other links stay as they are (shown as 早期关联的数据集).
    for experiment in list(Experiment.objects.filter(dataset__isnull=True).order_by("pk")):
        linked = [d for d in experiment.datasets.all() if d.owner_id == experiment.owner_id and d.kind in RAW_KINDS]
        own = linked[0] if len(linked) == 1 and linked[0].experiments.count() == 1 else None
        if own:
            experiment.datasets.remove(own)
        else:
            own = files_for(experiment.owner_id, experiment.project_id, experiment.title, "raw")
        Experiment.objects.filter(pk=experiment.pk).update(dataset=own)
        remember(experiment, "~", REASON)

    # 2. A raw dataset that no experiment shows becomes a draft experiment of its own.
    for dataset in list(Dataset.objects.filter(kind__in=RAW_KINDS, raw_of__isnull=True, experiments__isnull=True).order_by("pk")):
        experiment = Experiment.objects.create(
            owner_id=dataset.owner_id, project_id=dataset.project_id, title=dataset.name, steps=dataset.description,
            date=timezone.localdate(dataset.created_at), dataset=dataset,
        )
        Experiment.objects.filter(pk=experiment.pk).update(created_at=dataset.created_at, updated_at=dataset.updated_at)
        remember(experiment, "+", f"升级：由早期数据集 {code(dataset)} 生成", when=dataset.created_at)

    # 3. A run cites the experiment whose own raw data an input dataset now is, and has its own script and result files.
    for run in list(ProcessingRun.objects.order_by("pk")):
        for dataset in list(run.inputs.filter(raw_of__isnull=False).select_related("raw_of")):
            run.experiments.add(dataset.raw_of)
            run.inputs.remove(dataset)
        missing = {}
        if run.script_dataset_id is None:
            missing["script_dataset"] = files_for(run.owner_id, run.project_id, f"{run.title} · 脚本", "script")
        if run.output_dataset_id is None:
            missing["output_dataset"] = files_for(run.owner_id, run.project_id, f"{run.title} · 结果", "result")
        if missing:
            ProcessingRun.objects.filter(pk=run.pk).update(**missing)
            remember(run, "~", REASON)

    # 4. A script or result dataset that no record shows becomes a draft run of its own.
    unused = Dataset.objects.filter(
        kind__in=("script", "result"), raw_of__isnull=True, experiments__isnull=True, used_by_runs__isnull=True,
        script_of_runs__isnull=True, produced_by_runs__isnull=True, weekly_reports__isnull=True,
    )
    for dataset in list(unused.order_by("pk")):
        script = dataset.kind == "script"
        run = ProcessingRun.objects.create(
            owner_id=dataset.owner_id, project_id=dataset.project_id, title=dataset.name,
            method=dataset.description if script else "", conclusion="" if script else dataset.description,
            script_dataset=dataset if script else files_for(dataset.owner_id, dataset.project_id, f"{dataset.name} · 脚本", "script"),
            output_dataset=files_for(dataset.owner_id, dataset.project_id, f"{dataset.name} · 结果", "result") if script else dataset,
        )
        ProcessingRun.objects.filter(pk=run.pk).update(created_at=dataset.created_at, updated_at=dataset.updated_at)
        remember(run, "+", f"升级：由早期数据集 {code(dataset)} 生成", when=dataset.created_at)


class Migration(migrations.Migration):
    dependencies = [
        ("datasets", "0004_records_own_files"),
        ("reports", "0003_dataset_versions"),  # step 4 reads reports' links to datasets
        ("research", "0006_records_own_files"),
    ]

    # Not reversible as data: the schema can go back, the records and files made here stay.
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
