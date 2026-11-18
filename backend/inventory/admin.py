from django.contrib import admin

from .models import Consumable, StockTxn


class StockTxnInline(admin.TabularInline):
    model = StockTxn
    extra = 0


@admin.register(Consumable)
class ConsumableAdmin(admin.ModelAdmin):
    list_display = ["name", "spec", "unit", "group", "location", "safety_stock"]
    list_filter = ["group"]
    search_fields = ["name", "spec"]
    inlines = [StockTxnInline]
