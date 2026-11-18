from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import ResearchGroup, User


@admin.register(ResearchGroup)
class ResearchGroupAdmin(admin.ModelAdmin):
    list_display = ["name", "finance_email", "created_at"]


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ["username", "name", "group", "role", "is_active", "must_change_password"]
    list_filter = ["group", "role", "is_active"]
    search_fields = ["username", "name", "email"]
    fieldsets = BaseUserAdmin.fieldsets + (
        ("课题组信息", {"fields": ["group", "role", "name", "phone", "research_direction", "must_change_password"]}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (("课题组信息", {"fields": ["group", "role", "name"]}),)
