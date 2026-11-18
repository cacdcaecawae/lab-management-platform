from django.contrib import admin

from .models import Project, ProjectLog


class ProjectLogInline(admin.TabularInline):
    model = ProjectLog
    extra = 0


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ["name", "group", "leader", "stage", "status", "updated_at"]
    list_filter = ["group", "status"]
    search_fields = ["name"]
    filter_horizontal = ["members"]
    inlines = [ProjectLogInline]
