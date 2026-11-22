from pathlib import Path

from django.contrib.auth import password_validation
from rest_framework import serializers

from .models import User


class UserBriefSerializer(serializers.ModelSerializer):
    """{id, name} — the standard way to embed a user in other resources."""

    name = serializers.CharField(source="display_name", read_only=True)

    class Meta:
        model = User
        fields = ["id", "name"]


class MeSerializer(serializers.ModelSerializer):
    group = serializers.SerializerMethodField()
    is_supervisor = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "username", "name", "role", "is_supervisor", "is_superuser", "group",
            "email", "phone", "wechat", "research_direction", "must_change_password", "avatar_url",
        ]
        # PATCH /api/auth/me/ (个人信息): the person keeps their own contact details and research direction up to date.
        # Name, login name and role are set by managers / ops; a renamed account could pass as someone else.
        read_only_fields = ["username", "name", "role", "is_superuser", "must_change_password"]

    avatar_url = serializers.SerializerMethodField()

    def get_group(self, user):
        return {"id": user.group_id, "name": user.group.name} if user.group_id else None

    def get_avatar_url(self, user):
        # Every upload gets a new storage name, so ?v= makes the browser fetch the new picture.
        return f"/api/auth/me/avatar/?v={Path(user.avatar.name).stem}" if user.avatar else None


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False)


class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(trim_whitespace=False)
    new_password = serializers.CharField(trim_whitespace=False)

    def validate_old_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("原密码不正确")
        return value

    def validate(self, attrs):
        if attrs["old_password"] == attrs["new_password"]:
            raise serializers.ValidationError({"new_password": ["新密码不能与原密码相同"]})
        password_validation.validate_password(attrs["new_password"], self.context["request"].user)
        return attrs
