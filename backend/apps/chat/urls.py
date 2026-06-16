from django.urls import path

from .views import ChatMessageCreateView, ChatMessageListView, ChatSessionListCreateView, PptxPatchView

urlpatterns = [
    path("sessions/", ChatSessionListCreateView.as_view(), name="chat-sessions"),
    path(
        "sessions/<int:session_id>/messages/",
        ChatMessageListView.as_view(),
        name="chat-messages",
    ),
    path(
        "sessions/<int:session_id>/messages/send/",
        ChatMessageCreateView.as_view(),
        name="chat-message-send",
    ),
    # PPTX 셰이프 패치 + 슬라이드 재렌더링
    path("pptx-patch/", PptxPatchView.as_view(), name="pptx-patch"),
]
