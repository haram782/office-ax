from django.urls import path
from .views import (
    DashboardStatsView,
    DocumentUploadView,
    EmailInboxAttachmentView,
    EmailInboxView,
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
    path("email-inbox/", EmailInboxView.as_view(), name="email-inbox"),
    path("email-inbox/<int:pk>/attachment/", EmailInboxAttachmentView.as_view(), name="email-inbox-attachment"),
    path("dashboard/stats/", DashboardStatsView.as_view(), name="dashboard-stats"),
]
