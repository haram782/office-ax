from rest_framework import serializers

from apps.documents.serializers import UploadLogSerializer
from .models import ChatMessage, ChatSession


class ChatMessageSerializer(serializers.ModelSerializer):
    upload_log = UploadLogSerializer(read_only=True)

    class Meta:
        model = ChatMessage
        fields = ["id", "role", "content", "upload_log", "artifact_url", "has_snippet", "snippet_data", "created_at"]
        read_only_fields = fields


class ChatSessionSerializer(serializers.ModelSerializer):
    messages = ChatMessageSerializer(many=True, read_only=True)
    message_count = serializers.IntegerField(source="messages.count", read_only=True)

    class Meta:
        model = ChatSession
        fields = ["id", "title", "message_count", "messages", "created_at", "updated_at"]
        read_only_fields = fields


class ChatSessionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatSession
        fields = ["id", "title", "created_at"]
        read_only_fields = ["id", "created_at"]


class ChatMessageCreateSerializer(serializers.Serializer):
    content = serializers.CharField(required=False, allow_blank=True, default="")
    file = serializers.FileField(required=False)

    def validate(self, attrs):
        if not attrs.get("content") and not attrs.get("file"):
            raise serializers.ValidationError("content 또는 file 중 하나는 필수입니다.")
        return attrs
