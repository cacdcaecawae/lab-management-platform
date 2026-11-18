from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Approval, Attachment, Fund, PurchaseItem, PurchaseRequest, Reimbursement


@admin.register(Fund)
class FundAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "group", "owner", "active"]
    list_filter = ["group", "active"]
    search_fields = ["code", "name"]


class PurchaseItemInline(admin.TabularInline):
    model = PurchaseItem
    extra = 0


class ApprovalInline(admin.TabularInline):
    model = Approval
    extra = 0
    can_delete = False
    readonly_fields = ["stage", "reviewer", "verdict", "comment", "total", "created_at"]


class AttachmentInline(admin.TabularInline):
    model = Attachment
    extra = 0
    fields = ["kind", "name", "size", "uploaded_by", "created_at"]
    readonly_fields = fields


@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(SimpleHistoryAdmin):
    list_display = ["__str__", "owner", "fund", "status", "submitted_at"]
    list_filter = ["status", "owner__group"]
    inlines = [PurchaseItemInline, ApprovalInline, AttachmentInline]


@admin.register(Reimbursement)
class ReimbursementAdmin(SimpleHistoryAdmin):
    list_display = ["__str__", "owner", "fund", "category", "amount", "occurred_on", "status"]
    list_filter = ["status", "category", "owner__group"]
    inlines = [AttachmentInline]
