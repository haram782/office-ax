"""
채팅 메시지 수정 의도 감지 → patch plan 생성 통합 테스트.

검증하는 흐름:
  1. 채팅 뷰가 upload_id를 text_chat 태스크에 전달한다.
  2. notify_chat_response가 type="patch_intent" 결과를 받으면
     PatchPlanService.generate()를 호출한다.
  3. 생성된 DocumentVersion/DocumentChange가 DB에 저장된다.
  4. 어시스턴트 ChatMessage가 type="patch_plan" snippet_data로 저장된다.

4가지 관점:
  happy path   — 수정 의도 감지 → patch plan 생성 → ChatMessage snippet 저장
  boundary     — type="qa" 응답은 기존 텍스트 메시지로 처리 (patch plan 미생성)
  failure      — upload_log 없거나 status != DONE → 오류 ChatMessage 생성
  regression   — upload_id 없는 텍스트 메시지는 기존 동작 유지 (patch plan 미생성)
"""
import shutil
import tempfile
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.chat.models import ChatMessage, ChatSession
from apps.chat.tasks import notify_chat_response
from apps.documents.models import (
    DocumentChange,
    DocumentVersion,
    FileStructure,
    UploadLog,
)

User = get_user_model()

TEMP_MEDIA = tempfile.mkdtemp(prefix="office_ax_chat_intent_test_")


def teardown_module(_module):
    """모듈 종료 시 임시 storage 삭제."""
    shutil.rmtree(TEMP_MEDIA, ignore_errors=True)


# ── 공용 픽스처 헬퍼 ──────────────────────────────────────────────────────────

def _make_user(username: str):
    return User.objects.create_user(username=username, password="pw")


def _authed(user) -> APIClient:
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def _make_file_structure() -> FileStructure:
    return FileStructure.objects.create(
        hash="test_hash_chat_intent",
        source_type=FileStructure.SourceType.EXCEL,
        column_schema=[],
    )


def _make_done_upload(user) -> UploadLog:
    fs = _make_file_structure()
    return UploadLog.objects.create(
        user=user,
        file_structure=fs,
        original_filename="sales.xlsx",
        status=UploadLog.Status.DONE,
        result={
            "source_type": "excel",
            "summary": "매출 데이터 분석 완료",
            "errors": ["A2 날짜 형식 오류"],
            "snippet_data": {
                "corrections": [{"cell": "A2", "issue": "날짜 형식"}],
            },
        },
    )


def _make_session(user) -> ChatSession:
    return ChatSession.objects.create(user=user, title="테스트 세션")


def _make_user_message(session, upload_log=None) -> ChatMessage:
    """user 역할의 ChatMessage를 생성한다."""
    return ChatMessage.objects.create(
        session=session,
        role=ChatMessage.Role.USER,
        content="A2셀 날짜를 2026-01-01로 수정해줘",
        upload_log=upload_log,
    )


# 테스트용 mock patch plan
_MOCK_PATCH_PLAN = {
    "schema": "office_ax.patch_plan.v0",
    "plan_id": "plan_intent_test_001",
    "summary": "A2 날짜 형식 교정",
    "operations": [
        {
            "operation_id": "op_intent_001",
            "format": "excel",
            "operation": "replace_cell",
            "title": "A2 날짜 교체",
            "original": "20260101",
            "replacement": "2026-01-01",
            "reason": "YYYY-MM-DD 통일",
            "confidence": 0.95,
            "anchor": {"type": "cell", "sheet": "Sheet1", "cell": "A2"},
            "patch": {"method": "openpyxl_set_value", "value": "2026-01-01"},
            "risk": {"level": "low"},
        },
    ],
}


# ── happy path ────────────────────────────────────────────────────────────────

@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class ChatPatchIntentHappyPathTest(TestCase):
    """
    type="patch_intent" 결과를 받으면
    PatchPlanService.generate()를 호출해 DocumentVersion과 ChatMessage를 생성한다.
    """

    def setUp(self):
        self.user = _make_user("intent_happy_user")
        self.session = _make_session(self.user)
        self.upload = _make_done_upload(self.user)
        self.user_msg = _make_user_message(self.session, upload_log=self.upload)

    @patch("apps.documents.services.patch_plan._generate_patch_plan", return_value=_MOCK_PATCH_PLAN)
    def test_patch_intent_creates_document_version(self, _mock_llm):
        """patch_intent 결과 수신 시 DocumentVersion(draft)이 생성된다."""
        result = {
            "type": "patch_intent",
            "refined_prompt": "A2 셀 날짜를 2026-01-01로 교체",
            "upload_id": self.upload.pk,
            "summary": "",
            "errors": [],
            "source_type": "chat",
        }

        notify_chat_response(self.user_msg.pk, result)

        self.assertTrue(
            DocumentVersion.objects.filter(
                upload_log=self.upload,
                status=DocumentVersion.Status.DRAFT,
            ).exists(),
            "patch_intent 수신 시 draft DocumentVersion이 생성되어야 한다",
        )

    @patch("apps.documents.services.patch_plan._generate_patch_plan", return_value=_MOCK_PATCH_PLAN)
    def test_patch_intent_creates_document_changes(self, _mock_llm):
        """생성된 DocumentVersion에 DocumentChange 행이 저장된다."""
        result = {
            "type": "patch_intent",
            "refined_prompt": "A2 셀 날짜 교체",
            "upload_id": self.upload.pk,
            "summary": "",
            "errors": [],
            "source_type": "chat",
        }

        notify_chat_response(self.user_msg.pk, result)

        version = DocumentVersion.objects.get(
            upload_log=self.upload, status=DocumentVersion.Status.DRAFT
        )
        self.assertEqual(
            DocumentChange.objects.filter(version=version).count(),
            1,
            "operation 1건 → DocumentChange 1개가 생성되어야 한다",
        )

    @patch("apps.documents.services.patch_plan._generate_patch_plan", return_value=_MOCK_PATCH_PLAN)
    def test_patch_intent_creates_assistant_message_with_patch_plan_snippet(self, _mock_llm):
        """어시스턴트 ChatMessage가 type='patch_plan' snippet_data로 저장된다."""
        result = {
            "type": "patch_intent",
            "refined_prompt": "A2 셀 날짜 교체",
            "upload_id": self.upload.pk,
            "summary": "",
            "errors": [],
            "source_type": "chat",
        }

        notify_chat_response(self.user_msg.pk, result)

        assistant_msg = ChatMessage.objects.filter(
            session=self.session,
            role=ChatMessage.Role.ASSISTANT,
        ).last()

        self.assertIsNotNone(assistant_msg, "어시스턴트 메시지가 생성되어야 한다")
        self.assertTrue(assistant_msg.has_snippet, "has_snippet=True이어야 한다")
        self.assertEqual(
            assistant_msg.snippet_data.get("type"),
            "patch_plan",
            "snippet_data.type이 'patch_plan'이어야 한다",
        )
        self.assertIn("version_id", assistant_msg.snippet_data)
        self.assertIn("changes", assistant_msg.snippet_data)
        self.assertIsNotNone(assistant_msg.snippet_data.get("version_id"))


# ── boundary ─────────────────────────────────────────────────────────────────

@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class ChatQaResponseBoundaryTest(TestCase):
    """
    type="qa" 응답은 기존 텍스트 메시지로 처리된다.
    DocumentVersion/patch_plan snippet이 생성되어서는 안 된다.
    """

    def setUp(self):
        self.user = _make_user("intent_qa_user")
        self.session = _make_session(self.user)
        self.upload = _make_done_upload(self.user)
        self.user_msg = _make_user_message(self.session)

    def test_qa_type_creates_plain_assistant_message(self):
        """type='qa' 결과는 patch plan 없이 일반 텍스트 ChatMessage를 생성한다."""
        result = {
            "type": "qa",
            "reply": "이 파일은 매출 데이터 Excel 파일입니다.",
            "summary": "이 파일은 매출 데이터 Excel 파일입니다.",
            "errors": [],
            "source_type": "chat",
        }

        notify_chat_response(self.user_msg.pk, result)

        # DocumentVersion이 생성되지 않아야 한다
        self.assertFalse(
            DocumentVersion.objects.filter(upload_log=self.upload).exists(),
            "qa 응답에서는 DocumentVersion이 생성되면 안 된다",
        )

        # 어시스턴트 메시지는 생성되어야 하고 snippet은 patch_plan이 아니어야 한다
        assistant_msg = ChatMessage.objects.filter(
            session=self.session,
            role=ChatMessage.Role.ASSISTANT,
        ).last()
        self.assertIsNotNone(assistant_msg)
        self.assertNotEqual(
            (assistant_msg.snippet_data or {}).get("type"),
            "patch_plan",
            "qa 응답에서 snippet_data.type이 patch_plan이 되어선 안 된다",
        )


# ── failure ───────────────────────────────────────────────────────────────────

@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class ChatPatchIntentFailureTest(TestCase):
    """
    patch_intent이지만 upload_log 상태가 DONE이 아니거나 존재하지 않는 경우.
    예외를 전파하지 않고 오류 내용이 담긴 어시스턴트 ChatMessage를 생성한다.
    """

    def setUp(self):
        self.user = _make_user("intent_fail_user")
        self.session = _make_session(self.user)
        self.user_msg = _make_user_message(self.session)

    def test_nonexistent_upload_id_creates_error_message(self):
        """존재하지 않는 upload_id → 오류 어시스턴트 ChatMessage가 생성된다."""
        result = {
            "type": "patch_intent",
            "refined_prompt": "A2 셀 날짜 교체",
            "upload_id": 999_999,  # 존재하지 않는 ID
            "summary": "",
            "errors": [],
            "source_type": "chat",
        }

        # 예외 전파 없이 완료되어야 한다
        notify_chat_response(self.user_msg.pk, result)

        assistant_msg = ChatMessage.objects.filter(
            session=self.session,
            role=ChatMessage.Role.ASSISTANT,
        ).last()
        self.assertIsNotNone(assistant_msg, "오류 상황에도 어시스턴트 메시지가 생성되어야 한다")

    def test_upload_not_done_creates_error_message(self):
        """upload_log.status != DONE → 오류 어시스턴트 ChatMessage가 생성된다."""
        fs = FileStructure.objects.create(
            hash="test_hash_not_done_intent",
            source_type=FileStructure.SourceType.EXCEL,
            column_schema=[],
        )
        pending_upload = UploadLog.objects.create(
            user=self.user,
            file_structure=fs,
            original_filename="pending.xlsx",
            status=UploadLog.Status.PROCESSING,  # DONE이 아님
        )

        result = {
            "type": "patch_intent",
            "refined_prompt": "A2 셀 날짜 교체",
            "upload_id": pending_upload.pk,
            "summary": "",
            "errors": [],
            "source_type": "chat",
        }

        notify_chat_response(self.user_msg.pk, result)

        assistant_msg = ChatMessage.objects.filter(
            session=self.session,
            role=ChatMessage.Role.ASSISTANT,
        ).last()
        self.assertIsNotNone(assistant_msg, "오류 상황에도 어시스턴트 메시지가 생성되어야 한다")
        # DocumentVersion은 생성되지 않아야 한다
        self.assertFalse(
            DocumentVersion.objects.filter(upload_log=pending_upload).exists()
        )


# ── regression ────────────────────────────────────────────────────────────────

@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class ChatTextOnlyRegressionTest(TestCase):
    """
    upload_id 없는 순수 텍스트 채팅은 기존 동작을 유지한다.
    type 필드가 없는 결과도 기존 방식대로 처리된다.
    """

    def setUp(self):
        self.user = _make_user("intent_regression_user")
        self.session = _make_session(self.user)
        self.user_msg = _make_user_message(self.session)

    def test_no_type_field_falls_back_to_legacy_behavior(self):
        """type 필드 없는 결과는 기존 텍스트 ChatMessage 생성 로직을 따른다."""
        result = {
            # type 필드 없음 — 기존 notify_chat_response 형식
            "summary": "Excel 파일 분석 방법에 대해 설명드립니다.",
            "errors": [],
            "source_type": "chat",
        }

        notify_chat_response(self.user_msg.pk, result)

        assistant_msg = ChatMessage.objects.filter(
            session=self.session,
            role=ChatMessage.Role.ASSISTANT,
        ).last()
        self.assertIsNotNone(assistant_msg)
        self.assertIn(
            "Excel 파일 분석 방법에 대해 설명드립니다.",
            assistant_msg.content,
            "기존 summary 기반 응답이 content에 포함되어야 한다",
        )
        # patch_plan snippet이 생성되지 않아야 한다
        self.assertNotEqual(
            (assistant_msg.snippet_data or {}).get("type"),
            "patch_plan",
        )

    @patch("apps.chat.views.current_app.send_task")
    def test_view_passes_upload_id_to_text_chat_task(self, mock_send_task):
        """ChatMessageCreateView가 request body의 upload_id를 text_chat 태스크에 전달한다."""
        mock_send_task.return_value = MagicMock(id="fake-task-id")
        client = _authed(self.user)

        upload = _make_done_upload(self.user)

        resp = client.post(
            f"/api/v1/chat/sessions/{self.session.pk}/messages/send/",
            {"content": "A2셀을 수정해줘", "upload_id": upload.pk},
            format="json",
        )

        self.assertEqual(resp.status_code, 202)

        # send_task 호출 확인
        mock_send_task.assert_called_once()
        call_kwargs = mock_send_task.call_args[1].get("kwargs") or mock_send_task.call_args[0][1]
        self.assertEqual(
            call_kwargs.get("upload_id"),
            upload.pk,
            "text_chat 태스크에 upload_id가 전달되어야 한다",
        )
