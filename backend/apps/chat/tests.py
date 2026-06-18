"""
doc-viewer-remediation 변경 회귀 테스트.

검증 대상:
  1. notify_chat_response(async 경로): assistant ChatMessage.upload_log_id == user upload_log_id
  2. ChatMessageCreateView duplicate 경로: assistant ChatMessage.upload_log_id == dup_upload_log_id
"""
from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.documents.models import FileStructure, UploadLog
from apps.chat.models import ChatMessage, ChatSession
from apps.chat.tasks import notify_chat_response

User = get_user_model()


# ── 공통 픽스처 헬퍼 ────────────────────────────────────────────────────────────

def _make_user(username="tester"):
    return User.objects.create_user(username=username, password="pw")


def _make_session(user):
    return ChatSession.objects.create(user=user, title="테스트 세션")


def _make_upload_log(user, filename="test.xlsx", status=UploadLog.Status.PENDING):
    fs, _ = FileStructure.objects.get_or_create(
        hash="abc123",
        defaults={"source_type": FileStructure.SourceType.EXCEL, "column_schema": []},
    )
    return UploadLog.objects.create(
        user=user,
        file_structure=fs,
        original_filename=filename,
        status=status,
        file_hash="deadbeef",
    )


def _make_user_message(session, upload_log):
    return ChatMessage.objects.create(
        session=session,
        role=ChatMessage.Role.USER,
        content="",
        upload_log=upload_log,
    )


# ── 1. notify_chat_response: async 완료 경로 ────────────────────────────────────

class NotifyChatResponseUploadLogTest(TestCase):
    """
    정상 async 완료 경로에서 생성된 assistant ChatMessage가
    user 메시지의 upload_log를 그대로 참조하는지 검증.
    """

    def setUp(self):
        self.user = _make_user()
        self.session = _make_session(self.user)
        self.upload_log = _make_upload_log(self.user)
        self.user_msg = _make_user_message(self.session, self.upload_log)

    def test_assistant_message_upload_log_matches_user_upload_log(self):
        # given: 분석 완료 결과
        result = {
            "summary": "분석 완료",
            "source_type": "excel",
            "artifact_url": "/media/corrected.xlsx",
            "snippet_data": {},
            "errors": [],
        }

        # when: Celery task 콜백 실행
        notify_chat_response(self.user_msg.pk, result)

        # then: assistant 메시지의 upload_log_id가 user 업로드와 동일
        assistant = ChatMessage.objects.get(
            session=self.session,
            role=ChatMessage.Role.ASSISTANT,
        )
        self.assertEqual(
            assistant.upload_log_id,
            self.upload_log.pk,
            "async 완료 경로: assistant.upload_log_id가 user upload_log_id와 일치해야 함",
        )

    def test_upload_log_status_set_to_done(self):
        # upload_log.status가 DONE으로 갱신되는지도 함께 확인
        result = {"summary": "완료", "source_type": "excel"}
        notify_chat_response(self.user_msg.pk, result)

        self.upload_log.refresh_from_db()
        self.assertEqual(self.upload_log.status, UploadLog.Status.DONE)


# ── 2. duplicate 경로: views.py ─────────────────────────────────────────────────

class DuplicateUploadAssistantBindingTest(TestCase):
    """
    동일 파일 재업로드(중복) 경로에서 생성된 assistant ChatMessage가
    신규로 생성된 dup_upload_log를 참조하는지 검증.
    """

    def setUp(self):
        self.user = _make_user(username="dup_tester")
        self.session = _make_session(self.user)

        # 기존에 완료된 UploadLog (원본)
        fs, _ = FileStructure.objects.get_or_create(
            hash="dup_hash_001",
            defaults={"source_type": FileStructure.SourceType.EXCEL, "column_schema": []},
        )
        self.existing_log = UploadLog.objects.create(
            user=self.user,
            file_structure=fs,
            original_filename="original.xlsx",
            status=UploadLog.Status.DONE,
            file_hash="sha256same",
            result={
                "summary": "기존 결과",
                "source_type": "excel",
                "artifact_url": "/media/original.xlsx",
                "snippet_data": {},
            },
        )

    def test_duplicate_assistant_message_uses_new_upload_log(self):
        """
        duplicate 분기에서 생성하는 dup_upload_log의 id가
        assistant ChatMessage.upload_log_id로 저장되어야 한다.
        """
        from rest_framework.test import APIClient

        client = APIClient()
        # force_authenticate: 토큰/세션 없이 인증 통과
        client.force_authenticate(user=self.user)

        # 동일 SHA-256 파일을 다시 업로드하는 상황을 시뮬레이션
        with patch("apps.chat.views.compute_sha256", return_value="sha256same"), \
             patch("apps.chat.views.default_storage.save", return_value="uploads/dup.xlsx"), \
             patch("apps.chat.views.default_storage.delete"), \
             patch("apps.chat.views.os.path.join", return_value="/tmp/dup.xlsx"), \
             patch("apps.chat.views.extract_excel_columns", return_value=[]):

            file_data = SimpleUploadedFile("dup.xlsx", b"fake", content_type="application/vnd.ms-excel")
            response = client.post(
                f"/api/v1/chat/sessions/{self.session.pk}/messages/send/",
                {"file": file_data},
                format="multipart",
            )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["status"], "duplicate")

        # 생성된 dup_upload_log 찾기 (기존 log와 다른 새 레코드)
        dup_log = UploadLog.objects.exclude(pk=self.existing_log.pk).filter(
            user=self.user, file_hash="sha256same"
        ).first()
        self.assertIsNotNone(dup_log, "dup_upload_log가 생성되어야 함")

        # assistant 메시지가 dup_log를 참조하는지 확인
        assistant = ChatMessage.objects.filter(
            session=self.session,
            role=ChatMessage.Role.ASSISTANT,
        ).first()
        self.assertIsNotNone(assistant)
        self.assertEqual(
            assistant.upload_log_id,
            dup_log.pk,
            "duplicate 경로: assistant.upload_log_id가 새 dup_upload_log.id와 일치해야 함",
        )
