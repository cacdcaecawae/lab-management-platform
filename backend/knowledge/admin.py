from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Doc, DocVersion


class DocVersionInline(admin.TabularInline):
    model = DocVersion
    extra = 0
    fields = ["number", "name", "size", "sha256", "note", "uploaded_by", "created_at"]
    readonly_fields = fields


@admin.register(Doc)
class DocAdmin(SimpleHistoryAdmin):
    list_display = ["title", "category", "equipment", "group", "author", "updated_at"]
    list_filter = ["group", "category"]
    search_fields = ["title", "description"]
    inlines = [DocVersionInline]
