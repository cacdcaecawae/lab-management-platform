from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import ReportFeedback, WeeklyReport


class ReportFeedbackInline(admin.TabularInline):
    model = ReportFeedback
    extra = 0


@admin.register(WeeklyReport)
class WeeklyReportAdmin(SimpleHistoryAdmin):
    list_display = ["owner", "week_start", "status", "submitted_at"]
    list_filter = ["status", "week_start"]
    inlines = [ReportFeedbackInline]
