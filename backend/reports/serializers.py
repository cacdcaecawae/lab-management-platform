from rest_framework import serializers

from accounts.serializers import UserBriefSerializer
from datasets.models import Dataset
from datasets.serializers import DatasetBriefSerializer
from datasets.versions import add_pinned_versions
from research.models import Experiment, ProcessingRun
from research.serializers import ExperimentBriefSerializer, RunBriefSerializer

from .models import ReportFeedback, WeeklyReport


class WeeklyReportBriefSerializer(serializers.ModelSerializer):
    """Embedded in the workbench."""

    owner = UserBriefSerializer(read_only=True)

    class Meta:
        model = WeeklyReport
        fields = ["id", "owner", "week_start", "status", "submitted_at"]


def validate_monday(value):
    if value.weekday() != 0:
        raise serializers.ValidationError("必须是周一的日期。")


class OwnRecordField(serializers.PrimaryKeyRelatedField):
    """Only the requester's own records can be linked. Only the owner can write a report, so the
    requester is the report owner; other people's ids get the same "not found" error as missing ones."""

    def get_queryset(self):
        return super().get_queryset().filter(owner=self.context["request"].user)


class FeedbackSerializer(serializers.ModelSerializer):
    author = UserBriefSerializer(read_only=True)

    class Meta:
        model = ReportFeedback
        fields = ["id", "author", "verdict", "content", "created_at"]

    def validate(self, attrs):
        if attrs["verdict"] == ReportFeedback.Verdict.NEEDS_REVISION and not attrs.get("content"):
            raise serializers.ValidationError({"content": ["要求补充时必须写明需要补充的内容。"]})
        return attrs


class WeeklyReportSerializer(serializers.ModelSerializer):
    owner = UserBriefSerializer(read_only=True)
    experiments = ExperimentBriefSerializer(many=True, read_only=True)
    datasets = DatasetBriefSerializer(many=True, read_only=True)
    runs = RunBriefSerializer(many=True, read_only=True)
    feedback = FeedbackSerializer(many=True, read_only=True)
    experiment_ids = OwnRecordField(
        source="experiments", queryset=Experiment.objects.all(), many=True, write_only=True, required=False
    )
    dataset_ids = OwnRecordField(source="datasets", queryset=Dataset.objects.all(), many=True, write_only=True, required=False)
    run_ids = OwnRecordField(source="runs", queryset=ProcessingRun.objects.all(), many=True, write_only=True, required=False)

    class Meta:
        model = WeeklyReport
        fields = [
            "id", "owner", "week_start", "goals", "done", "findings", "next_plan",
            "experiments", "datasets", "runs", "experiment_ids", "dataset_ids", "run_ids",
            "status", "submitted_at", "feedback", "created_at", "updated_at",
        ]
        read_only_fields = ["status", "submitted_at", "created_at", "updated_at"]
        validators = []  # a duplicate week is a 409 raised by the view, not DRF's unique-together 400

    def to_representation(self, report):
        return add_pinned_versions(super().to_representation(report), report, ["datasets"])

    def validate_week_start(self, value):
        validate_monday(value)
        if self.instance is not None and value != self.instance.week_start:
            raise serializers.ValidationError("周报创建后不能修改所属周。")
        return value


class ReportQuerySerializer(serializers.Serializer):
    """Query-string params of the list and missing endpoints; parsed here so bad values are a 400, not a 500."""

    owner = serializers.IntegerField(required=False)
    week_start = serializers.DateField(required=False, validators=[validate_monday])
    status = serializers.ChoiceField(WeeklyReport.Status.choices, required=False)
