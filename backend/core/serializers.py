"""Brief (embedded) representations shared by several apps. See docs/api-contract.md."""

from rest_framework import serializers

from accounts.serializers import UserBriefSerializer
from datasets.models import Dataset
from datasets.versions import current_versions
from equipment.models import Equipment
from projects.models import Project
from reports.models import WeeklyReport
from research.models import Experiment, ProcessingRun


class ProjectBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ["id", "name"]


class EquipmentBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Equipment
        fields = ["id", "code", "name", "status"]


class DatasetBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dataset
        fields = ["id", "code", "name", "kind"]


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


class ExperimentBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Experiment
        fields = ["id", "code", "title", "status"]


class RunBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProcessingRun
        fields = ["id", "code", "title", "status"]


class WeeklyReportBriefSerializer(serializers.ModelSerializer):
    owner = UserBriefSerializer(read_only=True)

    class Meta:
        model = WeeklyReport
        fields = ["id", "owner", "week_start", "status", "submitted_at"]
