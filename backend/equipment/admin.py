from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Booking, Equipment, UsageReport


@admin.register(Equipment)
class EquipmentAdmin(SimpleHistoryAdmin):
    list_display = ["code", "name", "group", "model", "location", "status", "calibration_due"]
    list_filter = ["group", "status"]
    search_fields = ["code", "name"]


class UsageReportInline(admin.StackedInline):
    model = UsageReport
    extra = 0


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ["equipment", "user", "kind", "start_at", "end_at", "cancelled_at"]
    list_filter = ["kind", "equipment__group"]
    inlines = [UsageReportInline]
