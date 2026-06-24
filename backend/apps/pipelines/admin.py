from django.contrib import admin

from .models import Pipeline


@admin.register(Pipeline)
class PipelineAdmin(admin.ModelAdmin):
    list_display = ["name", "type", "is_active", "owner", "last_run_at", "created_at"]
    list_filter = ["type", "is_active"]
    search_fields = ["name", "owner__username"]
