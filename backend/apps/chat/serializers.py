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


class ConversationListSerializer(serializers.ModelSerializer):
    """
    대화 세션 목록 전용 직렬화 — messages 배열 미포함 (경량).
    목록 조회 시 N+1 쿼리와 페이로드 과다를 방지하기 위해 별도 분리.
    """

    message_count = serializers.IntegerField(source="messages.count", read_only=True)

    class Meta:
        model = ChatSession
        fields = ["id", "title", "message_count", "created_at", "updated_at"]
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
