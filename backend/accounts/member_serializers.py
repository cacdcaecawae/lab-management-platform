from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from rest_framework import serializers

from core.exceptions import Conflict

from .models import User

PRIVATE_FIELDS = ["username", "email", "phone", "wechat", "must_change_password"]
# Creating, renaming and signing up all say it the way the pages name the field (409 conflict).
LOGIN_NAME_TAKEN = "这个学号 / 工号已经有账号在用"


class LoginNameMixin:
    """Editing an account (the members page, 系统管理): the login name can be corrected, e.g. a student number mistyped
    at signup. Same format check as creating; taken by another account -> 409. Records point at the account, not the
    name, so nothing else changes; the person signs in with the new name from then on."""

    def validate_username(self, value):
        if User.objects.filter(username=value).exclude(pk=self.instance.pk).exists():
            raise Conflict(LOGIN_NAME_TAKEN)
        return value

    def update(self, user, validated_data):
        try:
            with transaction.atomic():
                return super().update(user, validated_data)
        except IntegrityError:  # a concurrent request took the name after validate_username
            raise Conflict(LOGIN_NAME_TAKEN)


STATUSES = {"active": "在籍", "graduated": "已毕业", "disabled": "已停用"}


class MemberDetailsMixin(serializers.Serializer):
    """Identity, year, status and tags (describe a person; no permissions), shared by the members page and 系统管理.
    `member_status` is written through is_active and graduated: only 在籍 signs in."""

    member_status = serializers.ChoiceField(choices=list(STATUSES), required=False)
    tags = serializers.ListField(child=serializers.CharField(max_length=20, allow_blank=True), max_length=10, required=False)

    def validate_tags(self, value):
        return list(dict.fromkeys(tag.strip() for tag in value if tag.strip()))  # in order, once each

    def validate_member_status(self, value):
        if value != "active" and self.instance is not None and self.instance == self.context["request"].user:
            raise serializers.ValidationError("不能停用自己的账号")
        return value

    def update(self, user, validated_data):
        status = validated_data.pop("member_status", None)
        if status:
            validated_data.update(is_active=status == "active", graduated=status == "graduated")
        return super().update(user, validated_data)


class MemberSerializer(LoginNameMixin, MemberDetailsMixin, serializers.ModelSerializer):
    """Member for everyone in the group; MemberDetail (private fields too) for supervisors and the member.
    Base role and the two tags are read-only here: ops sets them, and approvers the 管理员 tag (MemberViewSet.manager)."""

    class Meta:
        model = User
        fields = [
            "id", "name", "role", "is_manager", "is_approver", "identity", "enrollment_year", "member_status", "tags",
            "research_direction", "is_active", *PRIVATE_FIELDS,
        ]
        read_only_fields = ["role", "is_manager", "is_approver", "must_change_password"]
        # Keep the format check but drop DRF's UniqueValidator: duplicates are a 409, as when creating.
        extra_kwargs = {
            "name": {"allow_blank": False},
            "username": {"validators": [User.username_validator]},
            "enrollment_year": {"min_value": 1950, "max_value": 2100},
        }

    def to_representation(self, member):
        data = super().to_representation(member)
        viewer = self.context["request"].user
        if not (viewer.is_supervisor or viewer.pk == member.pk):
            for field in PRIVATE_FIELDS:
                data.pop(field)
        return data

    def validate_is_active(self, value):
        if not value and self.instance == self.context["request"].user:
            raise serializers.ValidationError("不能停用自己的账号")
        return value


class NewAccountMixin:
    """Creating an account, shared by the members page (a manager adds a student) and 系统管理 (ops adds any account):
    username taken -> 409, Django's password rules, and the initial password must be changed at the first login."""

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise Conflict(LOGIN_NAME_TAKEN)
        return value

    def validate(self, attrs):
        # Pass an unsaved user so UserAttributeSimilarityValidator can compare against username/name.
        candidate = User(**{k: v for k, v in attrs.items() if k != "password"})
        try:
            password_validation.validate_password(attrs["password"], candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": exc.messages})
        return attrs

    def create(self, validated_data):
        try:
            with transaction.atomic():
                return User.objects.create_user(**{"must_change_password": True, **validated_data})
        except IntegrityError:  # a concurrent request took the username after validate_username
            raise Conflict(LOGIN_NAME_TAKEN)


class MemberCreateSerializer(NewAccountMixin, MemberSerializer):
    """A manager adds a student (the base role's default); advisors and the tags are set by ops."""

    password = serializers.CharField(write_only=True, trim_whitespace=False)
    member_status = serializers.CharField(read_only=True)  # a new account is 在籍

    class Meta(MemberSerializer.Meta):
        fields = [*MemberSerializer.Meta.fields, "password"]
        read_only_fields = ["role", "is_manager", "is_approver", "is_active", "must_change_password"]
        # Keep the format check but drop DRF's UniqueValidator: duplicates are a 409, not a 400.
        extra_kwargs = {
            "name": {"required": True, "allow_blank": False},
            "username": {"validators": [User.username_validator]},
            "enrollment_year": {"min_value": 1950, "max_value": 2100},
        }

    def create(self, validated_data):
        return super().create({**validated_data, "group": self.context["request"].user.group})


class RegisterSerializer(NewAccountMixin, serializers.ModelSerializer):
    """A student registering through the group's link (the view checks the code first). They chose the password."""

    password = serializers.CharField(write_only=True, trim_whitespace=False)

    class Meta:
        model = User
        fields = ["username", "name", "email", "password"]
        extra_kwargs = {
            "name": {"required": True, "allow_blank": False},
            "username": {"validators": [User.username_validator]},
        }

    def create(self, validated_data):
        return super().create({
            **validated_data, "role": User.Role.STUDENT, "is_active": False, "pending": True, "must_change_password": False,
        })


class PendingMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "name", "email", "date_joined"]


class IdsSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False, max_length=100)


class PasswordResetSerializer(serializers.Serializer):
    password = serializers.CharField(trim_whitespace=False)

    def validate_password(self, value):
        password_validation.validate_password(value, self.instance)
        return value

    def update(self, user, validated_data):
        user.set_password(validated_data["password"])
        user.must_change_password = True  # a reset password is a new initial password
        user.save(update_fields=["password", "must_change_password"])
        return user
