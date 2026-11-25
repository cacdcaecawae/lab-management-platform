from django import forms
from django.contrib import admin
from django.db import transaction
from django.db.models import Q
from simple_history.admin import SimpleHistoryAdmin

from .models import ActionItem, AgendaItem, Meeting, MeetingFile, carry_order_error, lock_meeting_group


class AgendaItemInline(admin.TabularInline):
    model = AgendaItem
    extra = 0


def holds_carried(meeting):
    """Items carried into or out of this meeting. Deleting them here would lose an item or leave two open copies: the
    website's edit and delete put the pairs right (or refuse), the admin would not, so it does not delete them."""
    carried = Q(meeting=meeting) & (Q(carried_to__isnull=False) | Q(carried_from__isnull=False))
    return ActionItem.objects.filter(carried | Q(carried_to=meeting)).exists()


class ActionItemForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.carried_to_id:
            self.fields["done_at"].disabled = True

    def clean_done_at(self):
        # The admin widget displays minutes; keep the original timestamp when another field is saved.
        return self.instance.done_at if self.instance.carried_to_id else self.cleaned_data["done_at"]


class MeetingForm(forms.ModelForm):
    def clean_date(self):
        date = self.cleaned_data["date"]
        if self.instance.pk:
            lock_meeting_group(self.instance.group_id)
            if error := carry_order_error(self.instance, date):
                raise forms.ValidationError(error)
        return date


class ActionItemInline(admin.TabularInline):
    model = ActionItem
    form = ActionItemForm
    fk_name = "meeting"
    extra = 0
    readonly_fields = ["carried_to", "carried_from"]  # set by carrying over; editing them by hand breaks the pairs

    def has_delete_permission(self, request, obj=None):  # obj: the meeting
        return super().has_delete_permission(request, obj) and not (obj and holds_carried(obj))


class MeetingFileInline(admin.TabularInline):
    model = MeetingFile
    extra = 0
    fields = ["name", "size", "uploaded_by", "created_at"]
    readonly_fields = fields


@admin.register(Meeting)
class MeetingAdmin(SimpleHistoryAdmin):
    list_display = ["date", "title", "group", "created_by"]
    list_filter = ["group"]
    form = MeetingForm
    inlines = [AgendaItemInline, ActionItemInline, MeetingFileInline]

    @transaction.atomic
    def history_form_view(self, *args, **kwargs):
        # Django wraps the normal change form in a transaction; SimpleHistoryAdmin's revert form needs one too.
        return super().history_form_view(*args, **kwargs)

    def has_delete_permission(self, request, obj=None):  # also asked per meeting by the bulk "delete selected"
        return super().has_delete_permission(request, obj) and not (obj and holds_carried(obj))
