from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Defect, Specimen, SpecimenLoan


class DefectInline(admin.TabularInline):
    model = Defect
    extra = 0


@admin.register(Specimen)
class SpecimenAdmin(SimpleHistoryAdmin):
    list_display = ["code", "name", "group", "kind", "status", "defects_public"]
    list_filter = ["group", "kind", "status"]
    search_fields = ["code", "name"]
    inlines = [DefectInline]


@admin.register(SpecimenLoan)
class SpecimenLoanAdmin(admin.ModelAdmin):
    list_display = ["specimen", "borrower", "borrowed_at", "due_date", "returned_at"]
    list_filter = ["specimen__group"]
