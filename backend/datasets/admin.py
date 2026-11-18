from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import DataFile, Dataset


class DataFileInline(admin.TabularInline):
    model = DataFile
    extra = 0
    fields = ["name", "size", "sha256", "uploaded_by", "uploaded_at"]
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Dataset)
class DatasetAdmin(SimpleHistoryAdmin):
    list_display = ["__str__", "project", "owner", "kind", "created_at"]
    list_filter = ["kind", "project__group"]
    search_fields = ["name"]
    inlines = [DataFileInline]
