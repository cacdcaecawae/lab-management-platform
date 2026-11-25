from django.db.models import Q
from rest_framework import serializers

from accounts.serializers import UserBriefSerializer
from core.permissions import scope_research
from datasets.models import Dataset
from datasets.serializers import DatasetBriefSerializer
from datasets.versions import add_pinned_versions
from equipment.serializers import EquipmentBriefSerializer, GroupEquipmentField
from projects.serializers import GroupProjectField, ProjectBriefSerializer
from specimens.serializers import GroupSpecimenField, SpecimenBriefSerializer

from .models import Experiment, ExperimentPhoto, ProcessingRun


class ExperimentBriefSerializer(serializers.ModelSerializer):
    """Embedded in weekly reports and the workbench."""

    class Meta:
        model = Experiment
        fields = ["id", "code", "title", "status"]


class RunBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProcessingRun
        fields = ["id", "code", "title", "status"]


class OwnDatasetField(serializers.PrimaryKeyRelatedField):
    """A dataset id owned by the requesting user. Only the owner can write a record,
    so the requesting user is always the record owner. Someone else's id and a
    missing id get the same 400, which does not reveal whether the dataset exists."""

    def get_queryset(self):
        return Dataset.objects.filter(owner=self.context["request"].user)


class CitableExperimentField(serializers.PrimaryKeyRelatedField):
    """An experiment the requesting user may cite: their own, or one shared with them through a project
    (core.permissions.scope_research). Any other id gets the same 400 as a missing one. One the draft already cites
    stays, so the draft still saves after a teammate's record is returned; submitting names it (submit_errors)."""

    def get_queryset(self):
        citable = Q(pk__in=scope_research(Experiment.objects.all(), self.context["request"].user).values("pk"))
        if self.root.instance is not None:
            citable |= Q(pk__in=self.root.instance.experiments.values("pk"))
        return Experiment.objects.filter(citable)


class RecordSerializer(serializers.ModelSerializer):
    """Fields shared by experiments and processing runs."""

    project = ProjectBriefSerializer(read_only=True)
    project_id = GroupProjectField(source="project", write_only=True, required=False, allow_null=True)
    owner = UserBriefSerializer(read_only=True)

    def validate_params(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("必须是 JSON 对象")
        return value


class ExperimentPhotoSerializer(serializers.ModelSerializer):
    uploaded_by = UserBriefSerializer(read_only=True)
    url = serializers.SerializerMethodField()

    class Meta:
        model = ExperimentPhoto
        fields = ["id", "name", "size", "uploaded_by", "url", "created_at"]

    def get_url(self, photo):
        return f"/api/experiment-photos/{photo.id}/file/"


class ExperimentSerializer(RecordSerializer):
    dataset = DatasetBriefSerializer(read_only=True)  # the record's own raw data files
    datasets = DatasetBriefSerializer(many=True, read_only=True)  # linked before records held their own files
    dataset_ids = OwnDatasetField(source="datasets", many=True, write_only=True, required=False)
    photos = ExperimentPhotoSerializer(many=True, read_only=True)
    file_count = serializers.SerializerMethodField()
    equipment_item = EquipmentBriefSerializer(read_only=True)
    equipment_item_id = GroupEquipmentField(source="equipment_item", write_only=True, required=False, allow_null=True)
    specimen_items = SpecimenBriefSerializer(many=True, read_only=True)
    specimen_item_ids = GroupSpecimenField(source="specimen_items", many=True, write_only=True, required=False)

    class Meta:
        model = Experiment
        fields = [
            "id", "code", "project", "project_id", "owner", "title", "date", "equipment_item", "equipment_item_id",
            "equipment", "specimen", "specimen_items", "specimen_item_ids",
            "params", "steps", "anomalies", "dataset", "datasets", "dataset_ids", "photos", "file_count",
            "status", "submitted_at", "created_at", "updated_at",
        ]
        read_only_fields = ["status", "submitted_at"]

    def get_file_count(self, experiment):
        if hasattr(experiment, "file_count"):  # annotated by the viewset's queryset
            return experiment.file_count
        return experiment.dataset.files.count() if experiment.dataset_id else 0  # a record just saved

    def to_representation(self, experiment):
        return add_pinned_versions(super().to_representation(experiment), experiment, ["dataset", "datasets"])


class CitedExperimentSerializer(serializers.ModelSerializer):
    """An experiment a run cites. dataset_id is its raw data, whose version the run pins on submit."""

    owner = UserBriefSerializer(read_only=True)
    dataset_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Experiment
        fields = ["id", "code", "title", "status", "owner", "dataset_id"]


class ProcessingRunSerializer(RecordSerializer):
    experiments = CitedExperimentSerializer(many=True, read_only=True)
    experiment_ids = CitableExperimentField(source="experiments", many=True, write_only=True, required=False)
    inputs = DatasetBriefSerializer(many=True, read_only=True)  # cited before runs cited experiments
    input_ids = OwnDatasetField(source="inputs", many=True, write_only=True, required=False)
    script_dataset = DatasetBriefSerializer(read_only=True)
    # Set when the run is created; a copy passes its source's, so both runs share the uploaded scripts.
    script_dataset_id = OwnDatasetField(source="script_dataset", write_only=True, required=False)
    output_dataset = DatasetBriefSerializer(read_only=True)
    output_dataset_id = OwnDatasetField(source="output_dataset", write_only=True, required=False)

    class Meta:
        model = ProcessingRun
        fields = [
            "id", "code", "project", "project_id", "owner", "title", "experiments", "experiment_ids",
            "inputs", "input_ids", "script_dataset", "script_dataset_id", "script_repo", "script_commit", "script_path",
            "method", "method_version", "params", "environment", "output_dataset", "output_dataset_id",
            "conclusion", "status", "submitted_at", "created_at", "updated_at",
        ]
        read_only_fields = ["status", "submitted_at"]

    def to_representation(self, run):
        fields = [("experiments", "dataset_id"), "inputs", "script_dataset", "output_dataset"]
        return add_pinned_versions(super().to_representation(run), run, fields)

    def validate_script_dataset_id(self, dataset):
        if dataset.kind != Dataset.Kind.SCRIPT:
            raise serializers.ValidationError("脚本必须是“脚本”类型的数据集")
        return dataset

    def validate_output_dataset_id(self, dataset):
        if dataset.kind != Dataset.Kind.RESULT:
            raise serializers.ValidationError("结果必须是“处理结果”类型的数据集")
        return dataset


class ReturnSerializer(serializers.Serializer):
    reason = serializers.CharField()
