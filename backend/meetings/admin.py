from django import forms
from django.contrib import admin
from django.db.models import Q
from simple_history.admin import SimpleHistoryAdmin

from .models import ActionItem, AgendaItem, Meeting, MeetingFile, carry_order_error


class AgendaItemInline(admin.TabularInline):
    model = AgendaItem
    extra = 0


def holds_carried(meeting):
    """Items carried into or out of this meeting. Deleting them here would lose an item or leave two open copies: the
    website's edit and delete put the pairs right (or refuse), the admin would not, so it does not delete them."""
    carried = Q(meeting=meeting) & (Q(carried_to__isnull=False) | Q(carried_from__isnull=False))
    return ActionItem.objects.filter(carried | Q(carried_to=meeting)).exists()


class ActionItemForm(forms.ModelForm):
    def clean(self):
        cleaned = super().clean()
        # reopened here while its copy carries on in the later meeting, it would be one item open twice
        if self.instance.carried_to_id and "done_at" in self.changed_data:
            raise forms.ValidationError(f"已转入 {self.instance.carried_to.date} 的组会，完成状态在那边改")
        return cleaned


class MeetingForm(forms.ModelForm):
    def clean_date(self):
        date = self.cleaned_data["date"]
        if self.instance.pk and (error := carry_order_error(self.instance, date)):
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

    def has_delete_permission(self, request, obj=None):  # also asked per meeting by the bulk "delete selected"
        return super().has_delete_permission(request, obj) and not (obj and holds_carried(obj))
