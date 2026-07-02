from django.contrib import admin

from .models import FileStructure, InboundEmail, IngestionWorkflow, UploadLog, UsageEvent


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


@admin.register(InboundEmail)
class InboundEmailAdmin(admin.ModelAdmin):
    list_display  = ["id", "user", "sender", "subject_short", "attachment_filename", "status", "received_at"]
    list_filter   = ["status"]
    search_fields = ["sender", "subject", "user__username"]
    readonly_fields = ["received_at"]

    @admin.display(description="제목 (앞 40자)")
    def subject_short(self, obj):
        return (obj.subject[:40] + "…") if len(obj.subject) > 40 else obj.subject


@admin.register(IngestionWorkflow)
class IngestionWorkflowAdmin(admin.ModelAdmin):
    list_display  = ["id", "user", "is_suggested", "is_active", "notification_channel", "activated_at"]
    list_filter   = ["is_active", "is_suggested", "notification_channel"]
    search_fields = ["user__username", "inbound_email"]
    readonly_fields = ["inbound_email", "activated_at", "suggested_at"]


@admin.register(UsageEvent)
class UsageEventAdmin(admin.ModelAdmin):
    list_display = [
        "id", "user", "event_type", "provider", "model", "status",
        "input_tokens", "output_tokens", "estimated_cost", "created_at",
    ]
    list_filter = ["user", "event_type", "provider", "status", "created_at"]
    search_fields = ["user__username", "provider", "model"]
    readonly_fields = [
        "user", "upload_log", "document_version", "chat_session", "event_type",
        "provider", "model", "input_tokens", "output_tokens", "token_source",
        "estimated_cost", "latency_ms", "status", "metadata", "created_at",
    ]
    ordering = ["-created_at"]
