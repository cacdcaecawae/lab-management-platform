"""系统管理 (ops account only): mail settings, research groups, member accounts of every group."""

from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from accounts.member_serializers import NewAccountMixin
from accounts.models import ResearchGroup, User
from core.models import SiteSettings


class MailSettingsSerializer(serializers.ModelSerializer):
    # Write-only: no response ever carries it. Blank keeps the stored one.
    mail_password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    password_set = serializers.SerializerMethodField()

    class Meta:
        model = SiteSettings
        fields = [
            "mail_enabled", "mail_host", "mail_port", "mail_security", "mail_username", "mail_password", "mail_from",
            "password_set", "last_mail_error", "last_mail_error_at",
        ]
        read_only_fields = ["last_mail_error", "last_mail_error_at"]

    def get_password_set(self, config):
        return bool(config.mail_password)

    def validate(self, attrs):
        def value(name):
            return attrs.get(name, getattr(self.instance, name))

        # Also while mail is off: a test mail is sent with the saved settings before mail is switched on.
        if value("mail_username") and "@" not in value("mail_username") and not value("mail_from"):
            raise serializers.ValidationError({"mail_from": ["账号不是邮箱地址时，请填写发件人地址"]})
        if value("mail_enabled"):
            if not value("mail_host"):
                raise serializers.ValidationError({"mail_host": ["启用邮件时必须填写 SMTP 服务器"]})
            if not value("mail_from") and "@" not in value("mail_username"):
                raise serializers.ValidationError({"mail_from": ["账号不是邮箱地址时，请填写发件人地址"]})
            if value("mail_username") and not (attrs.get("mail_password") or self.instance.mail_password):
                raise serializers.ValidationError({"mail_password": ["请填写授权码"]})
        return attrs

    def update(self, config, validated_data):
        password = validated_data.pop("mail_password", "")
        if password and password != config.mail_password:
            config.mail_password = password
            config._change_reason = "修改了授权码"  # the code itself is not kept in the history
        return super().update(config, validated_data)


class MailTestSerializer(serializers.Serializer):
    to = serializers.EmailField()


class SystemGroupSerializer(serializers.ModelSerializer):
    member_count = serializers.SerializerMethodField()

    class Meta:
        model = ResearchGroup
        fields = ["id", "name", "finance_email", "member_count", "created_at"]
        extra_kwargs = {"name": {"validators": [UniqueValidator(ResearchGroup.objects.all(), message="已有同名的课题组")]}}

    def get_member_count(self, group):
        return getattr(group, "member_count", 0)  # annotated by the view: active members


class AccountSerializer(serializers.ModelSerializer):
    """A member account of any group. The group is set when the account is created: moving someone changes who
    can see their records, so that stays a deliberate step in /admin/."""

    group = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "username", "name", "role", "group", "email", "phone", "research_direction", "is_active",
            "must_change_password", "pending", "last_login",
        ]
        read_only_fields = ["username", "must_change_password", "pending", "last_login"]
        extra_kwargs = {"name": {"allow_blank": False}}

    def get_group(self, user):
        return {"id": user.group_id, "name": user.group.name} if user.group_id else None

    def update(self, user, validated_data):
        if validated_data.get("is_active"):
            validated_data["pending"] = False  # ops switching an applicant on is an approval
        return super().update(user, validated_data)


class AccountCreateSerializer(NewAccountMixin, AccountSerializer):
    group_id = serializers.PrimaryKeyRelatedField(source="group", queryset=ResearchGroup.objects.all(), write_only=True)
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    class Meta(AccountSerializer.Meta):
        fields = [*AccountSerializer.Meta.fields, "group_id", "password"]
        read_only_fields = ["is_active", "must_change_password", "pending", "last_login"]
        # Keep the format check but drop DRF's UniqueValidator: duplicates are a 409, as on the members page.
        extra_kwargs = {
            "name": {"required": True, "allow_blank": False},
            "role": {"required": True},
            "username": {"validators": [User.username_validator]},
        }

