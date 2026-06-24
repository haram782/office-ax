"""
documents 앱 신규 기능 테스트.

커버 범위:
  1. GET /api/v1/email-inbox/ — 수신 이메일 이력 조회 (본인 것만)
  2. 인바운드 이메일 웹훅 수신 시 InboundEmail 레코드 자동 생성
  3. 인증 없이 이메일 이력 접근 시 401 반환
"""
import json
from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from apps.documents.models import FileStructure, IngestionWorkflow

User = get_user_model()


def _make_user(username="inbox_tester"):
    return User.objects.create_user(username=username, password="pw")


def _authed_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _make_workflow(user, inbound_email="user-1-abc@officeax.com"):
    """활성 IngestionWorkflow 픽스처 생성."""
    fs, _ = FileStructure.objects.get_or_create(
        hash="inbox_hash_001",
        defaults={"source_type": FileStructure.SourceType.EXCEL, "column_schema": []},
    )
    return IngestionWorkflow.objects.create(
        user=user,
        file_structure=fs,
        is_suggested=True,
        is_active=True,
        notification_channel=IngestionWorkflow.NotificationChannel.KAKAO,
        inbound_email=inbound_email,
    )


class EmailInboxListTest(TestCase):
    """GET /api/v1/email-inbox/ 테스트."""

    def setUp(self):
        self.user = _make_user()
        self.client = _authed_client(self.user)

    def test_empty_inbox(self):
        """수신 이메일이 없으면 빈 배열 반환."""
        response = self.client.get("/api/v1/email-inbox/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_unauthenticated_returns_401(self):
        """인증 없이 접근 시 401 반환."""
        response = APIClient().get("/api/v1/email-inbox/")
        self.assertEqual(response.status_code, 401)

    def test_inbox_shows_only_own_emails(self):
        """다른 유저의 이메일 이력은 노출되지 않는다."""
        from apps.documents.models import InboundEmail

        other_user = _make_user(username="inbox_other")
        workflow = _make_workflow(self.user)
        other_workflow = _make_workflow(other_user, inbound_email="user-2-xyz@officeax.com")

        # 본인 이메일 이력 생성
        InboundEmail.objects.create(
            workflow=workflow,
            user=self.user,
            sender="sender@example.com",
            subject="내 이메일",
            received_at=None,
        )
        # 타인 이메일 이력 생성
        InboundEmail.objects.create(
            workflow=other_workflow,
            user=other_user,
            sender="other@example.com",
            subject="타인 이메일",
            received_at=None,
        )

        response = self.client.get("/api/v1/email-inbox/")
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["subject"], "내 이메일")

    def test_inbox_response_fields(self):
        """응답 필드: sender, subject, attachment_filename, received_at, status 포함 검증."""
        from apps.documents.models import InboundEmail

        workflow = _make_workflow(self.user)
        InboundEmail.objects.create(
            workflow=workflow,
            user=self.user,
            sender="sender@example.com",
            subject="테스트 제목",
            attachment_filename="report.xlsx",
        )

        response = self.client.get("/api/v1/email-inbox/")
        self.assertEqual(response.status_code, 200)
        record = response.data[0]
        for field in ["sender", "subject", "attachment_filename", "received_at", "status"]:
            self.assertIn(field, record, f"{field} 필드가 응답에 없습니다")
        self.assertEqual(record["sender"], "sender@example.com")
        self.assertEqual(record["attachment_filename"], "report.xlsx")


class InboundEmailWebhookSavesRecordTest(TestCase):
    """
    POST /api/v1/inbound-email/ 웹훅 수신 시
    InboundEmail 레코드가 생성되는지 검증.
    """

    def setUp(self):
        self.user = _make_user(username="webhook_inbox")
        self.workflow = _make_workflow(self.user, inbound_email="user-99-test@officeax.com")

    def _post_webhook(self, attachment_name="report.xlsx"):
        """SendGrid Inbound Parse 형식 웹훅 POST 시뮬레이션."""
        envelope = json.dumps({"to": ["user-99-test@officeax.com"], "from": "boss@corp.com"})
        attachment_info = json.dumps({
            "attachment1": {"filename": attachment_name, "type": "application/vnd.ms-excel"},
        })
        file_data = SimpleUploadedFile(attachment_name, b"fake excel", content_type="application/vnd.ms-excel")

        # INBOUND_WEBHOOK_SECRET를 빈 문자열로 강제해 개발 환경 모드(검증 스킵)를 활성화
        with patch.dict("os.environ", {"INBOUND_WEBHOOK_SECRET": ""}), \
             patch("apps.documents.views.save_temp_file", return_value="/tmp/fake.xlsx"), \
             patch("apps.documents.views.current_app.send_task") as mock_task:
            mock_task.return_value = MagicMock(id="fake-task-id")
            response = self.client.post(
                "/api/v1/inbound-email/",
                {
                    "envelope": envelope,
                    "to": "user-99-test@officeax.com",
                    "from": "boss@corp.com",
                    "subject": "월간 보고서",
                    "attachments": "1",
                    "attachment-info": attachment_info,
                    "attachment1": file_data,
                },
                format="multipart",
            )
        return response

    def test_webhook_creates_inbound_email_record(self):
        """웹훅 수신 후 InboundEmail 레코드가 생성되어야 한다."""
        from apps.documents.models import InboundEmail

        response = self._post_webhook()
        self.assertEqual(response.status_code, 200)

        record = InboundEmail.objects.filter(user=self.user).first()
        self.assertIsNotNone(record, "InboundEmail 레코드가 생성되어야 합니다")
        self.assertEqual(record.sender, "boss@corp.com")
        self.assertEqual(record.subject, "월간 보고서")
        self.assertEqual(record.attachment_filename, "report.xlsx")
