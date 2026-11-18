from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Experiment, ProcessingRun


@admin.register(Experiment)
class ExperimentAdmin(SimpleHistoryAdmin):
    list_display = ["__str__", "project", "owner", "date", "status"]
    list_filter = ["status", "project__group"]
    search_fields = ["title"]


@admin.register(ProcessingRun)
class ProcessingRunAdmin(SimpleHistoryAdmin):
    list_display = ["__str__", "project", "owner", "environment", "status"]
    list_filter = ["status", "project__group"]
    search_fields = ["title"]
