from django.contrib import admin

from .models import Consumable, StockTxn


class StockTxnInline(admin.TabularInline):
    model = StockTxn
    extra = 0
    fields = ("kind", "quantity", "handler", "project", "purchase", "note", "created_at")
    readonly_fields = fields

    # Ledger revisions rely on immutable entries. Corrections use the locked API's adjust action.
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Consumable)
class ConsumableAdmin(admin.ModelAdmin):
    list_display = ["name", "spec", "unit", "group", "location", "safety_stock"]
    list_filter = ["group"]
    search_fields = ["name", "spec"]
    inlines = [StockTxnInline]
