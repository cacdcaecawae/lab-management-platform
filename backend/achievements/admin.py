from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Achievement


@admin.register(Achievement)
class AchievementAdmin(SimpleHistoryAdmin):
    list_display = ["title", "type", "status", "date", "group", "created_by"]
    list_filter = ["group", "type", "status"]
    search_fields = ["title", "authors", "venue"]
