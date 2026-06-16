from django.urls import path
from .views import (
    DocumentUploadView,
    InboundEmailWebhookView,
    UploadListView,
    UploadResultView,
    WorkflowListView,
    WorkflowActivateView,
)

urlpatterns = [
    path("uploads/", DocumentUploadView.as_view(), name="upload-create"),
    path("uploads/history/", UploadListView.as_view(), name="upload-list"),
    path("uploads/<int:pk>/", UploadResultView.as_view(), name="upload-result"),
    path("workflows/", WorkflowListView.as_view(), name="workflow-list"),
    path("workflows/<int:pk>/activate/", WorkflowActivateView.as_view(), name="workflow-activate"),
    # SendGrid Inbound Parse 웹훅 — 인증 없이 수신, 내부 시크릿+DB로 검증
    path("inbound-email/", InboundEmailWebhookView.as_view(), name="inbound-email"),
]
