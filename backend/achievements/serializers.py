from rest_framework import serializers

from accounts.serializers import UserBriefSerializer
from projects.serializers import AnyGroupMemberField

from .models import STATUSES, Achievement


class AchievementSerializer(serializers.ModelSerializer):
    members = UserBriefSerializer(many=True, read_only=True)
    member_ids = AnyGroupMemberField(source="members", many=True, write_only=True, required=False)
    created_by = UserBriefSerializer(read_only=True)
    fulltext_url = serializers.SerializerMethodField()

    class Meta:
        model = Achievement
        fields = [
            "id", "type", "title", "authors", "members", "member_ids", "venue", "date", "status", "link",
            "fulltext_name", "fulltext_url", "notes", "created_by", "created_at", "updated_at",
        ]
        read_only_fields = ["fulltext_name"]

    def get_fulltext_url(self, achievement):
        return f"/api/achievements/{achievement.id}/fulltext/" if achievement.fulltext else None

    def validate(self, attrs):
        kind = attrs.get("type", getattr(self.instance, "type", None))
        status = attrs.get("status", getattr(self.instance, "status", None))
        if status not in STATUSES.get(kind, []):
            allowed = "、".join(s.label for s in STATUSES.get(kind, []))
            raise serializers.ValidationError({"status": [f"{Achievement.Type(kind).label}的状态只能是：{allowed}"]})
        return attrs
