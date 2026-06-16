from django.contrib import admin

from .models import ChatMessage, ChatSession, UserActionLog


@admin.register(UserActionLog)
class UserActionLogAdmin(admin.ModelAdmin):
    list_display   = ["id", "user", "action_type", "file_type", "action_tag", "upload_log_id", "created_at"]
    list_filter    = ["action_type", "file_type"]
    search_fields  = ["user__username", "action_tag"]
    readonly_fields = ["created_at", "meta", "upload_log", "session"]
    ordering = ["-created_at"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user", "session", "upload_log")


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display  = ["id", "user", "title", "created_at", "updated_at"]
    search_fields = ["user__username", "title"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display  = ["id", "session", "role", "has_snippet", "artifact_url_short", "created_at"]
    list_filter   = ["role", "has_snippet"]
    search_fields = ["content", "session__user__username"]
    readonly_fields = ["created_at", "snippet_data"]

    @admin.display(description="artifact_url")
    def artifact_url_short(self, obj):
        return obj.artifact_url[-40:] if obj.artifact_url else "—"
