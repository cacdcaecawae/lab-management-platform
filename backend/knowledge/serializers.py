from rest_framework import serializers

from accounts.serializers import UserBriefSerializer
from core.serializers import EquipmentBriefSerializer
from equipment.serializers import GroupEquipmentField

from .models import Doc, DocVersion

MAX_TAGS = 10


class DocVersionSerializer(serializers.ModelSerializer):
    uploaded_by = UserBriefSerializer(read_only=True)
    url = serializers.SerializerMethodField()

    class Meta:
        model = DocVersion
        fields = ["id", "number", "name", "size", "sha256", "note", "uploaded_by", "url", "created_at"]

    def get_url(self, version):
        return f"/api/docs/{version.doc_id}/versions/{version.number}/file/"


class DocSerializer(serializers.ModelSerializer):
    author = UserBriefSerializer(read_only=True)
    equipment = EquipmentBriefSerializer(read_only=True)
    equipment_id = GroupEquipmentField(source="equipment", write_only=True, required=False, allow_null=True)
    tags = serializers.ListField(child=serializers.CharField(max_length=30, allow_blank=True), required=False)
    latest = serializers.SerializerMethodField()

    class Meta:
        model = Doc
        fields = [
            "id", "title", "category", "equipment", "equipment_id", "tags", "description", "author", "latest",
            "created_at", "updated_at",
        ]

    def validate_tags(self, tags):
        tags = list(dict.fromkeys(t.strip() for t in tags if t.strip()))  # trimmed, no blanks, no repeats, in order
        if len(tags) > MAX_TAGS:
            raise serializers.ValidationError(f"标签最多 {MAX_TAGS} 个")
        return tags

    def get_latest(self, doc):
        versions = doc.versions.all()  # prefetched, newest first
        return DocVersionSerializer(versions[0]).data if versions else None


class DocDetailSerializer(DocSerializer):
    versions = DocVersionSerializer(many=True, read_only=True)

    class Meta(DocSerializer.Meta):
        fields = [*DocSerializer.Meta.fields, "versions"]
