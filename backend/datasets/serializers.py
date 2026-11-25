from django.urls import reverse
from rest_framework import serializers

from accounts.serializers import UserBriefSerializer
from core.permissions import scope_group
from core.preview import preview_kind
from projects.models import Project
from projects.serializers import ProjectBriefSerializer

from .models import DataFile, Dataset
from .versions import current_version


class DatasetBriefSerializer(serializers.ModelSerializer):
    """Embedded in experiments, runs and reports; see versions.add_pinned_versions."""

    class Meta:
        model = Dataset
        fields = ["id", "code", "name", "kind"]


class DatasetSerializer(serializers.ModelSerializer):
    project = ProjectBriefSerializer(read_only=True)
    project_id = serializers.PrimaryKeyRelatedField(
        source="project", queryset=Project.objects.none(), write_only=True, required=False, allow_null=True
    )
    owner = UserBriefSerializer(read_only=True)
    # Filled by the viewset's annotate(); instances must come from DatasetViewSet.get_queryset().
    file_count = serializers.IntegerField(read_only=True)
    total_size = serializers.IntegerField(read_only=True)
    version = serializers.SerializerMethodField()

    class Meta:
        model = Dataset
        fields = [
            "id", "code", "project", "project_id", "owner", "name", "kind", "description",
            "file_count", "total_size", "version", "created_at", "updated_at",
        ]

    def get_version(self, dataset):
        return current_version(dataset)

    def get_fields(self):
        fields = super().get_fields()
        if self.instance is None:
            fields["project_id"].queryset = scope_group(Project.objects.all(), self.context["request"].user)
        else:
            # project and kind are fixed at creation; PATCH ignores them.
            fields["project_id"].read_only = fields["kind"].read_only = True
        return fields


class DataFileSerializer(serializers.ModelSerializer):
    dataset_id = serializers.IntegerField(read_only=True)
    uploaded_by = UserBriefSerializer(read_only=True)
    download_url = serializers.SerializerMethodField()
    preview_url = serializers.SerializerMethodField()
    preview_kind = serializers.SerializerMethodField()
    # In a version a submitted record pins: no longer deletable. Context "locked": the ids, from versions.locked_file_ids.
    locked = serializers.SerializerMethodField()

    class Meta:
        model = DataFile
        fields = [
            "id", "dataset_id", "name", "size", "sha256", "uploaded_by", "uploaded_at",
            "download_url", "preview_url", "preview_kind", "locked",
        ]

    def get_locked(self, obj):
        return obj.pk in self.context.get("locked", ())

    def get_download_url(self, obj):
        return reverse("datafile-download", args=[obj.pk])

    def get_preview_url(self, obj):
        return reverse("datafile-preview", args=[obj.pk])

    def get_preview_kind(self, obj):
        return preview_kind(obj.name)
