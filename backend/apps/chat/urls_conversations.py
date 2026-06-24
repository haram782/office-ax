from django.urls import path

from .views_conversations import ConversationListCreateView, ConversationMessageListView

urlpatterns = [
    path("conversations/", ConversationListCreateView.as_view(), name="conversation-list"),
    path("conversations/<int:pk>/messages/", ConversationMessageListView.as_view(), name="conversation-messages"),
]
