from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import ActionItem, AgendaItem, Meeting, MeetingFile


class AgendaItemInline(admin.TabularInline):
    model = AgendaItem
    extra = 0


class ActionItemInline(admin.TabularInline):
    model = ActionItem
    fk_name = "meeting"
    extra = 0


class MeetingFileInline(admin.TabularInline):
    model = MeetingFile
    extra = 0
    fields = ["name", "size", "uploaded_by", "created_at"]
    readonly_fields = fields


@admin.register(Meeting)
class MeetingAdmin(SimpleHistoryAdmin):
    list_display = ["date", "title", "group", "created_by"]
    list_filter = ["group"]
    inlines = [AgendaItemInline, ActionItemInline, MeetingFileInline]
