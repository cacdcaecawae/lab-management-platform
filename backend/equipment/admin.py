from django import forms
from django.contrib import admin
from django.core.files.uploadedfile import UploadedFile
from django.utils import timezone
from simple_history.admin import SimpleHistoryAdmin

from .models import Booking, Equipment, UsageReport


@admin.register(Equipment)
class EquipmentAdmin(SimpleHistoryAdmin):
    list_display = ["code", "name", "group", "model", "location", "status", "calibration_due"]
    list_filter = ["group", "status"]
    search_fields = ["code", "name"]


class UsageReportInlineForm(forms.ModelForm):
    class Meta:
        model = UsageReport
        fields = ("condition", "description", "photo")

    def save(self, commit=True):
        obj = super().save(commit=False)
        photo = self.cleaned_data.get("photo")
        if isinstance(photo, UploadedFile):
            obj.photo_size = photo.size
            obj.photo_uploaded_at = timezone.now()
        elif photo is False:
            obj.photo_size = None
            obj.photo_uploaded_at = None
        if commit:
            obj.save()
            self.save_m2m()
        return obj


class UsageReportInline(admin.StackedInline):
    model = UsageReport
    form = UsageReportInlineForm
    extra = 0


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ["equipment", "user", "kind", "start_at", "end_at", "cancelled_at"]
    list_filter = ["kind", "equipment__group"]
    inlines = [UsageReportInline]
