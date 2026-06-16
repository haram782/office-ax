from django.contrib import admin

from .models import FileStructure, IngestionWorkflow, UploadLog


@admin.register(UploadLog)
class UploadLogAdmin(admin.ModelAdmin):
    list_display  = ["id", "user", "original_filename", "status", "file_hash_short", "uploaded_at"]
    list_filter   = ["status", "file_structure__source_type"]
    search_fields = ["original_filename", "user__username", "file_hash"]
    readonly_fields = ["file_hash", "ax_task_id", "uploaded_at", "result", "file"]
    ordering = ["-uploaded_at"]

    @admin.display(description="SHA-256 (앞 12자)")
    def file_hash_short(self, obj):
        return (obj.file_hash[:12] + "…") if obj.file_hash else "—"


@admin.register(FileStructure)
class FileStructureAdmin(admin.ModelAdmin):
    list_display  = ["id", "source_type", "hash_short", "created_at"]
    list_filter   = ["source_type"]
    search_fields = ["hash"]
    readonly_fields = ["hash", "created_at"]

    @admin.display(description="해시 (앞 12자)")
    def hash_short(self, obj):
        return obj.hash[:12] + "…"


@admin.register(IngestionWorkflow)
class IngestionWorkflowAdmin(admin.ModelAdmin):
    list_display  = ["id", "user", "is_suggested", "is_active", "notification_channel", "activated_at"]
    list_filter   = ["is_active", "is_suggested", "notification_channel"]
    search_fields = ["user__username", "inbound_email"]
    readonly_fields = ["inbound_email", "activated_at", "suggested_at"]
