from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from rest_framework import serializers

from core.exceptions import Conflict

from .models import User

PRIVATE_FIELDS = ["username", "email", "phone", "must_change_password"]
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


class MemberSerializer(LoginNameMixin, serializers.ModelSerializer):
    """Member for everyone in the group; MemberDetail (private fields too) for supervisors and the member."""

    class Meta:
        model = User
        fields = ["id", "name", "role", "research_direction", "is_active", *PRIVATE_FIELDS]
        read_only_fields = ["must_change_password"]
        # Keep the format check but drop DRF's UniqueValidator: duplicates are a 409, as when creating.
        extra_kwargs = {"name": {"allow_blank": False}, "username": {"validators": [User.username_validator]}}

    def to_representation(self, member):
        data = super().to_representation(member)
        viewer = self.context["request"].user
        if not (viewer.is_supervisor or viewer.pk == member.pk):
            for field in PRIVATE_FIELDS:
                data.pop(field)
        return data

    def validate_role(self, value):
        user = self.context["request"].user
        if self.instance == user:
            if value != user.role:
                raise serializers.ValidationError("不能修改自己的角色")
        elif value != User.Role.STUDENT:
            raise serializers.ValidationError("管理员只能设置学生账号；导师和管理员账号请联系运维在“系统管理”里设置")
        return value

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
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    class Meta(MemberSerializer.Meta):
        fields = [*MemberSerializer.Meta.fields, "password"]
        read_only_fields = ["is_active", "must_change_password"]
        # Keep the format check but drop DRF's UniqueValidator: duplicates are a 409, not a 400.
        extra_kwargs = {
            "name": {"required": True, "allow_blank": False},
            "role": {"required": True},
            "username": {"validators": [User.username_validator]},
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
