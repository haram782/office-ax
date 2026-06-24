"""
email-inbox 첨부파일 URL 반환 API 테스트.

커버 범위:
  1. GET /api/v1/email-inbox/:id/attachment/ — upload_log.file URL 반환
  2. upload_log 없는 이메일 → 404 반환
  3. 타인 이메일 → 404
  4. 인증 없이 → 401
"""
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient
from unittest.mock import patch

from apps.documents.models import FileStructure, InboundEmail, IngestionWorkflow, UploadLog

User = get_user_model()


def _make_user(username="att_tester"):
    return User.objects.create_user(username=username, password="pw")


def _authed_client(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def _make_workflow(user):
    fs, _ = FileStructure.objects.get_or_create(
        hash="att_hash",
        defaults={"source_type": FileStructure.SourceType.EXCEL, "column_schema": []},
    )
    return IngestionWorkflow.objects.create(
        user=user, file_structure=fs, is_active=True,
        notification_channel=IngestionWorkflow.NotificationChannel.KAKAO,
        inbound_email="att-test@officeax.com",
    )


def _make_upload_log(user, with_file=True):
    fs, _ = FileStructure.objects.get_or_create(
        hash="att_hash",
        defaults={"source_type": FileStructure.SourceType.EXCEL, "column_schema": []},
    )
    log = UploadLog.objects.create(
        user=user, file_structure=fs,
        original_filename="report.xlsx", status=UploadLog.Status.DONE,
    )
    if with_file:
        log.file = SimpleUploadedFile("report.xlsx", b"fake", content_type="application/vnd.ms-excel")
        log.save(update_fields=["file"])
    return log


class EmailInboxAttachmentTest(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.client = _authed_client(self.user)
        self.workflow = _make_workflow(self.user)

    def _make_inbox(self, upload_log=None):
        return InboundEmail.objects.create(
            workflow=self.workflow, user=self.user,
            sender="boss@corp.com", subject="첨부 테스트",
            attachment_filename="report.xlsx",
            upload_log=upload_log,
        )

    def test_returns_file_url(self):
        """upload_log.file 이 있으면 file_url을 반환한다."""
        upload_log = _make_upload_log(self.user)
        inbox = self._make_inbox(upload_log=upload_log)

        # storage.exists를 True로 모킹해 URL 반환을 보장
        with patch("apps.documents.serializers.UploadLog.file.field.storage.exists", return_value=True):
            response = self.client.get(f"/api/v1/email-inbox/{inbox.pk}/attachment/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("file_url", response.data)

    def test_no_upload_log_returns_404(self):
        """upload_log 없는 이메일에 첨부파일 요청 시 404 반환."""
        inbox = self._make_inbox(upload_log=None)
        response = self.client.get(f"/api/v1/email-inbox/{inbox.pk}/attachment/")
        self.assertEqual(response.status_code, 404)

    def test_other_user_cannot_access(self):
        """타인의 이메일 첨부파일에 접근 불가 (404)."""
        other = _make_user(username="att_other")
        upload_log = _make_upload_log(other)
        other_inbox = InboundEmail.objects.create(
            user=other, sender="x@x.com", subject="타인",
            upload_log=upload_log,
        )
        response = self.client.get(f"/api/v1/email-inbox/{other_inbox.pk}/attachment/")
        self.assertEqual(response.status_code, 404)

    def test_unauthenticated_returns_401(self):
        """인증 없이 접근 시 401 반환."""
        inbox = self._make_inbox()
        response = APIClient().get(f"/api/v1/email-inbox/{inbox.pk}/attachment/")
        self.assertEqual(response.status_code, 401)
