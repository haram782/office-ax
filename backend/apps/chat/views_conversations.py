from rest_framework import status
from rest_framework.generics import ListCreateAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ChatMessage, ChatSession
from .serializers import (
    ChatMessageSerializer,
    ChatSessionCreateSerializer,
    ConversationListSerializer,
)


class ConversationListCreateView(ListCreateAPIView):
    """
    GET  /api/v1/conversations/ — 본인 대화 세션 목록 (messages 미포함, 경량)
    POST /api/v1/conversations/ — 새 대화 세션 생성
    """

    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ChatSessionCreateSerializer
        return ConversationListSerializer

    def get_queryset(self):
        return ChatSession.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = ChatSessionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        session = ChatSession.objects.create(
            user=request.user,
            title=serializer.validated_data.get("title", ""),
        )
        return Response(
            ChatSessionCreateSerializer(session).data,
            status=status.HTTP_201_CREATED,
        )


class ConversationMessageListView(APIView):
    """
    GET /api/v1/conversations/:id/messages/
    세션 메시지 이력 반환 — 본인 세션만 접근 가능.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk: int):
        # 세션 소유권 확인 — 타인 세션이면 404
        try:
            ChatSession.objects.get(pk=pk, user=request.user)
        except ChatSession.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        messages = (
            ChatMessage.objects
            .filter(session_id=pk)
            .select_related("upload_log")
            .order_by("created_at")
        )
        return Response(ChatMessageSerializer(messages, many=True).data)
