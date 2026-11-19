from rest_framework import serializers

from accounts.serializers import UserBriefSerializer
from datasets.models import Dataset
from datasets.serializers import DatasetBriefSerializer
from datasets.versions import add_pinned_versions
from equipment.serializers import EquipmentBriefSerializer, GroupEquipmentField
from projects.serializers import GroupProjectField, ProjectBriefSerializer

from .models import Experiment, ProcessingRun


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


class RecordSerializer(serializers.ModelSerializer):
    """Fields shared by experiments and processing runs."""

    project = ProjectBriefSerializer(read_only=True)
    project_id = GroupProjectField(source="project", write_only=True)
    owner = UserBriefSerializer(read_only=True)

    def validate_params(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("必须是 JSON 对象")
        return value


class ExperimentSerializer(RecordSerializer):
    datasets = DatasetBriefSerializer(many=True, read_only=True)
    dataset_ids = OwnDatasetField(source="datasets", many=True, write_only=True, required=False)
    equipment_item = EquipmentBriefSerializer(read_only=True)
    equipment_item_id = GroupEquipmentField(source="equipment_item", write_only=True, required=False, allow_null=True)

    class Meta:
        model = Experiment
        fields = [
            "id", "code", "project", "project_id", "owner", "title", "date", "equipment_item", "equipment_item_id",
            "equipment", "specimen",
            "params", "steps", "anomalies", "datasets", "dataset_ids", "status", "submitted_at",
            "created_at", "updated_at",
        ]
        read_only_fields = ["status", "submitted_at"]

    def to_representation(self, experiment):
        return add_pinned_versions(super().to_representation(experiment), experiment, ["datasets"])


class ProcessingRunSerializer(RecordSerializer):
    inputs = DatasetBriefSerializer(many=True, read_only=True)
    input_ids = OwnDatasetField(source="inputs", many=True, write_only=True, required=False)
    script_dataset = DatasetBriefSerializer(read_only=True)
    script_dataset_id = OwnDatasetField(source="script_dataset", write_only=True, required=False, allow_null=True)
    output_dataset = DatasetBriefSerializer(read_only=True)
    output_dataset_id = OwnDatasetField(source="output_dataset", write_only=True, required=False, allow_null=True)

    class Meta:
        model = ProcessingRun
        fields = [
            "id", "code", "project", "project_id", "owner", "title", "inputs", "input_ids",
            "script_dataset", "script_dataset_id", "script_repo", "script_commit", "script_path",
            "method_version", "params", "environment", "output_dataset", "output_dataset_id",
            "conclusion", "status", "submitted_at", "created_at", "updated_at",
        ]
        read_only_fields = ["status", "submitted_at"]

    def to_representation(self, run):
        return add_pinned_versions(super().to_representation(run), run, ["inputs", "script_dataset", "output_dataset"])

    def validate_script_dataset_id(self, dataset):
        if dataset and dataset.kind != Dataset.Kind.SCRIPT:
            raise serializers.ValidationError("脚本必须是“脚本”类型的数据集")
        return dataset

    def validate_output_dataset_id(self, dataset):
        if dataset and dataset.kind != Dataset.Kind.RESULT:
            raise serializers.ValidationError("结果必须是“处理结果”类型的数据集")
        return dataset


class ReturnSerializer(serializers.Serializer):
    reason = serializers.CharField()
