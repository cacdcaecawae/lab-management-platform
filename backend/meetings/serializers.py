from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from accounts.serializers import UserBriefSerializer
from core.exceptions import Conflict
from core.notifications import notify
from projects.serializers import AnyGroupMemberField

from .models import ActionItem, AgendaItem, Meeting, MeetingFile


def require_item_fields(serializer, attrs, names):
    """Root PATCH skips DRF required checks, but newly created children still need them."""
    errors = {
        name: [serializer.fields[name].error_messages["required"]]
        for name in names
        if serializer.fields[name].source not in attrs
    }
    if errors:
        raise serializers.ValidationError(errors, code="required")
    return attrs


class AgendaItemSerializer(serializers.ModelSerializer):
    presenter = UserBriefSerializer(read_only=True)
    presenter_id = AnyGroupMemberField(source="presenter", write_only=True)

    def validate(self, attrs):
        # The agenda is replaced, so every row is a new record even on PATCH.
        return require_item_fields(self, attrs, ("presenter_id", "topic"))

    class Meta:
        model = AgendaItem
        fields = ["id", "presenter", "presenter_id", "topic"]


class ActionItemSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)  # an existing item when the meeting is edited
    owner = UserBriefSerializer(read_only=True)
    owner_id = AnyGroupMemberField(source="owner", write_only=True)
    # A new item copied from an open item of an earlier meeting: that one is marked as carried over here.
    carried_from = serializers.IntegerField(min_value=1, required=False, write_only=True)
    carried_to = serializers.SerializerMethodField()

    def validate(self, attrs):
        if "id" not in attrs:
            return require_item_fields(self, attrs, ("owner_id", "content"))
        return attrs

    def get_carried_to(self, item):
        return {"id": item.carried_to_id, "date": item.carried_to.date.isoformat()} if item.carried_to_id else None

    class Meta:
        model = ActionItem
        fields = ["id", "owner", "owner_id", "content", "due_date", "done_at", "carried_from", "carried_to"]
        read_only_fields = ["done_at"]


class MyActionItemSerializer(ActionItemSerializer):
    """For the workbench: which meeting the item came from."""

    meeting = serializers.SerializerMethodField()

    class Meta(ActionItemSerializer.Meta):
        fields = [*ActionItemSerializer.Meta.fields, "meeting"]

    def get_meeting(self, item):
        return {"id": item.meeting_id, "date": item.meeting.date.isoformat(), "title": item.meeting.title}


class MeetingFileSerializer(serializers.ModelSerializer):
    uploaded_by = UserBriefSerializer(read_only=True)
    url = serializers.SerializerMethodField()

    class Meta:
        model = MeetingFile
        fields = ["id", "name", "size", "uploaded_by", "url", "created_at"]

    def get_url(self, meeting_file):
        return f"/api/meeting-files/{meeting_file.id}/file/"


class MeetingSerializer(serializers.ModelSerializer):
    created_by = UserBriefSerializer(read_only=True)
    agenda = AgendaItemSerializer(many=True, required=False)
    actions = ActionItemSerializer(many=True, required=False)
    files = MeetingFileSerializer(many=True, read_only=True)

    class Meta:
        model = Meeting
        fields = ["id", "date", "title", "minutes", "agenda", "actions", "files", "created_by", "created_at", "updated_at"]

    def validate_actions(self, actions):
        known = set(self.instance.actions.values_list("id", flat=True)) if self.instance else set()
        unknown = [a["id"] for a in actions if "id" in a and a["id"] not in known]
        if unknown:
            raise serializers.ValidationError(f"行动项不属于这次组会：{unknown}")
        return actions

    @transaction.atomic
    def create(self, validated_data):
        agenda, actions = validated_data.pop("agenda", []), validated_data.pop("actions", [])
        meeting = super().create(validated_data)
        self._write_agenda(meeting, agenda)
        self._notify_presenters(meeting, {a["presenter"].pk for a in agenda})
        carried = self._carry(meeting, actions)
        ActionItem.objects.bulk_create(ActionItem(meeting=meeting, **a) for a in actions)
        self._notify_assignees(meeting, {a["owner"].pk for a in actions} - carried)
        return meeting

    @transaction.atomic
    def update(self, meeting, validated_data):
        agenda, actions = validated_data.pop("agenda", None), validated_data.pop("actions", None)
        meeting = super().update(meeting, validated_data)
        if agenda is not None:  # the list replaces the agenda
            presenting = set(meeting.agenda.values_list("presenter_id", flat=True))
            meeting.agenda.all().delete()
            self._write_agenda(meeting, agenda)
            self._notify_presenters(meeting, {a["presenter"].pk for a in agenda} - presenting)
        if actions is not None:
            # Matched by id so an item keeps its "done" state; items left out are removed.
            kept = {a["id"] for a in actions if "id" in a}
            # The meeting save locks its row until commit, so another edit cannot run before this read.
            previous_owners = dict(meeting.actions.filter(pk__in=kept).values_list("pk", "owner_id"))
            assigned = set()
            carried = self._carry(meeting, actions)
            meeting.actions.exclude(id__in=kept).delete()
            for a in actions:
                fields = {k: v for k, v in a.items() if k != "id"}
                if "id" in a:
                    changed = meeting.actions.filter(pk=a["id"]).update(**fields)
                    if changed and "owner" in a and previous_owners.get(a["id"]) != a["owner"].pk:
                        assigned.add(a["owner"].pk)
                else:
                    ActionItem.objects.create(meeting=meeting, **fields)
                    assigned.add(a["owner"].pk)
            self._notify_assignees(meeting, assigned - carried)
        return meeting

    @staticmethod
    def _carry(meeting, actions):
        """Mark the earlier items that new rows were copied from as carried over to this meeting (done there). Returns
        the owners of those rows: their work is not new, so they are not notified again. The items are locked first, so
        two meetings saved at once cannot both carry one; one already done or carried makes the save a 409."""
        sources = {a.pop("carried_from") for a in actions if "carried_from" in a}
        if not sources:
            return set()
        earlier = list(
            ActionItem.objects.select_for_update(of=("self",))
            .filter(pk__in=sources, meeting__group_id=meeting.group_id)
            .exclude(meeting=meeting)
            .order_by("pk")
        )
        if taken := next((item for item in earlier if item.done_at or item.carried_to_id), None):
            raise Conflict(f"“{taken.content}”已经完成或转入别的组会，请删掉这一行，或重新带入", code="invalid_state")
        ActionItem.objects.filter(pk__in=[item.pk for item in earlier]).update(done_at=timezone.now(), carried_to=meeting)
        return {item.owner_id for item in earlier}

    @staticmethod
    def _notify_assignees(meeting, owner_ids):
        if owner_ids:
            notify(meeting.group_id, "有新的组会行动项分配给你", f"/meetings/{meeting.pk}", recipient_ids=owner_ids)

    def _notify_presenters(self, meeting, presenter_ids):
        request = self.context.get("request")
        exclude = [request.user.pk] if request else []
        if presenter_ids:
            notify(meeting.group_id, "你在组会上有汇报", f"/meetings/{meeting.pk}", recipient_ids=presenter_ids,
                   exclude_ids=exclude, body=f"{meeting.date} {meeting.title}")

    @staticmethod
    def _write_agenda(meeting, agenda):
        AgendaItem.objects.bulk_create(AgendaItem(meeting=meeting, order=i, **item) for i, item in enumerate(agenda))
