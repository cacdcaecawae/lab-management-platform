from django.db import IntegrityError, transaction
from rest_framework import serializers

from accounts.serializers import UserBriefSerializer
from core.exceptions import Conflict
from core.permissions import is_supervisor, scope_group
from projects.serializers import GroupMemberField, GroupProjectField, ProjectBriefSerializer

from .models import Defect, Specimen, SpecimenLoan


class SpecimenBriefSerializer(serializers.ModelSerializer):
    """Embedded in experiments. Never carries defects."""

    class Meta:
        model = Specimen
        fields = ["id", "code", "name", "status"]


class GroupSpecimenField(serializers.PrimaryKeyRelatedField):
    """A specimen id from the requesting user's research group."""

    def get_queryset(self):
        return scope_group(Specimen.objects.all(), self.context["request"].user)


class DefectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Defect
        fields = ["id", "kind", "size_mm", "depth_mm", "position", "note"]


class LoanSerializer(serializers.ModelSerializer):
    borrower = UserBriefSerializer(read_only=True)
    project = ProjectBriefSerializer(read_only=True)
    project_id = GroupProjectField(source="project", write_only=True, required=False, allow_null=True)
    returned_by = UserBriefSerializer(read_only=True)

    class Meta:
        model = SpecimenLoan
        fields = [
            "id", "borrower", "project", "project_id", "purpose", "due_date", "borrowed_at", "returned_at", "returned_by",
            "return_note",
        ]
        read_only_fields = ["borrowed_at", "returned_at", "return_note"]


class ReturnSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


def defects_visible(user, specimen):
    """Defect values may be a blind test's answer: students see them only once a manager made them public."""
    return specimen.defects_public or is_supervisor(user)


DEFECT_FIELDS = ("kind", "size_mm", "depth_mm", "position", "note")


def defect_rows(defects):
    """Validated defects as comparable tuples (Decimal("2") == Decimal("2.00"), so stored values compare equal)."""
    return [(d["kind"], d.get("size_mm"), d.get("depth_mm"), d.get("position", ""), d.get("note", "")) for d in defects]


class SpecimenSerializer(serializers.ModelSerializer):
    custodian = UserBriefSerializer(read_only=True)
    custodian_id = GroupMemberField(source="custodian", write_only=True, required=False, allow_null=True)
    defects = DefectSerializer(many=True, required=False)
    current_loan = serializers.SerializerMethodField()

    class Meta:
        model = Specimen
        fields = [
            "id", "code", "name", "kind", "material", "dimensions", "location", "custodian", "custodian_id", "status",
            "defects_public", "defects", "current_loan", "notes", "created_at", "updated_at",
        ]

    def get_current_loan(self, specimen):
        # SpecimenViewSet prefetches open_loans; a just-saved instance asks the database.
        loans = getattr(specimen, "open_loans", None)
        if loans is None:
            loans = specimen.loans.filter(returned_at__isnull=True).select_related("borrower", "project")
        loan = next(iter(loans), None)
        return LoanSerializer(loan).data if loan else None

    def to_representation(self, specimen):
        data = super().to_representation(specimen)
        if not defects_visible(self.context["request"].user, specimen):
            data["defects"] = None  # hidden, not empty: and no count either, which would give part of the answer away
        return data

    def validate_code(self, value):
        same_code = scope_group(Specimen.objects.filter(code=value), self.context["request"].user)
        if self.instance:
            same_code = same_code.exclude(pk=self.instance.pk)
        if same_code.exists():
            raise Conflict("本组已有相同编号的试件")
        return value

    def save(self, **kwargs):
        try:
            with transaction.atomic():
                return super().save(**kwargs)
        except IntegrityError:  # a concurrent request took the same code after validate_code
            raise Conflict("本组已有相同编号的试件")

    def create(self, validated_data):
        defects = validated_data.pop("defects", [])
        specimen = super().create(validated_data)
        Defect.objects.bulk_create(Defect(specimen=specimen, **d) for d in defects)
        return specimen

    def update(self, instance, validated_data):
        defects = validated_data.pop("defects", None)
        # Under the row lock (inside save()'s transaction), like a borrow: a status change and a borrow do not interleave.
        locked = Specimen.objects.select_for_update().get(pk=instance.pk)
        if defects is not None and defect_rows(defects) != list(locked.defects.values_list(*DEFECT_FIELDS)):
            locked._change_reason = "修改了缺陷参数"  # the history says that, never the values
            locked.defects.all().delete()
            Defect.objects.bulk_create(Defect(specimen=locked, **d) for d in defects)
        return super().update(locked, validated_data)
