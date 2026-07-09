"""
채팅 메시지 수정 의도 감지 → patch plan 생성 통합 테스트.

검증하는 흐름:
  1. 채팅 뷰가 upload_id를 text_chat 태스크에 전달한다.
  2. notify_chat_response가 type="patch_intent" 결과를 받으면
     ax-engine tasks.generate_patch_plan을 enqueue한다.
  3. notify_patch_plan_generated 콜백이 생성된 PatchPlan을 저장한다.
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
from apps.chat.tasks import notify_chat_response, notify_patch_plan_generated
from apps.documents.models import (
    DocumentChange,
    DocumentVersion,
    FileStructure,
    UploadLog,
    UsageEvent,
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

_MOCK_EMPTY_PATCH_PLAN = {
    "schema": "office_ax.patch_plan.v0",
    "plan_id": "plan_empty_intent_001",
    "summary": "수정 항목 없음",
    "operations": [],
}


# ── happy path ────────────────────────────────────────────────────────────────

@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class ChatPatchIntentHappyPathTest(TestCase):
    """
    type="patch_intent" 결과를 받으면
    ax-engine PatchPlan 태스크를 enqueue하고, 완료 콜백에서 DB 저장을 수행한다.
    """

    def setUp(self):
        self.user = _make_user("intent_happy_user")
        self.session = _make_session(self.user)
        self.upload = _make_done_upload(self.user)
        self.user_msg = _make_user_message(self.session, upload_log=self.upload)

    @patch("apps.chat.tasks.current_app.send_task")
    def test_patch_intent_enqueues_generate_patch_plan_task(self, mock_send_task):
        """patch_intent 결과 수신 시 ax-engine PatchPlan 태스크가 enqueue된다."""
        result = {
            "type": "patch_intent",
            "refined_prompt": "A2 셀 날짜를 2026-01-01로 교체",
            "upload_id": self.upload.pk,
            "summary": "",
            "errors": [],
            "source_type": "chat",
        }

        notify_chat_response(self.user_msg.pk, result)

        mock_send_task.assert_called_once()
        self.assertEqual(mock_send_task.call_args.args[0], "tasks.generate_patch_plan")
        kwargs = mock_send_task.call_args.kwargs["kwargs"]
        self.assertEqual(kwargs["prompt"], "A2 셀 날짜를 2026-01-01로 교체")
        self.assertEqual(kwargs["callback_task"], "chat.notify_patch_plan_generated")
        self.assertEqual(kwargs["callback_kwargs"]["upload_id"], self.upload.pk)
        self.assertEqual(
            mock_send_task.call_args.kwargs["queue"],
            "ax",
            "PatchPlan LLM 호출은 ax-engine 큐로 보내야 한다",
        )
        self.assertFalse(
            DocumentVersion.objects.filter(
                upload_log=self.upload,
                status=DocumentVersion.Status.DRAFT,
            ).exists(),
            "enqueue 단계에서는 아직 draft DocumentVersion이 생성되면 안 된다",
        )

    def test_patch_plan_callback_creates_document_changes(self):
        """ax-engine 콜백 수신 시 DocumentVersion과 DocumentChange가 저장된다."""
        notify_patch_plan_generated(
            chat_message_id=self.user_msg.pk,
            upload_id=self.upload.pk,
            prompt="A2 셀 날짜 교체",
            result=_MOCK_PATCH_PLAN,
        )

        version = DocumentVersion.objects.get(
            upload_log=self.upload, status=DocumentVersion.Status.DRAFT
        )
        self.assertEqual(
            DocumentChange.objects.filter(version=version).count(),
            1,
            "operation 1건 → DocumentChange 1개가 생성되어야 한다",
        )

    def test_patch_plan_callback_creates_assistant_message_with_patch_plan_snippet(self):
        """완료 콜백이 type='patch_plan' snippet_data를 가진 어시스턴트 메시지를 저장한다."""
        notify_patch_plan_generated(
            chat_message_id=self.user_msg.pk,
            upload_id=self.upload.pk,
            prompt="A2 셀 날짜 교체",
            result=_MOCK_PATCH_PLAN,
        )

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

    def test_empty_patch_plan_callback_creates_terminal_patch_plan_snippet(self):
        """operations=[] 결과도 프론트 폴링 종료용 patch_plan snippet을 저장한다."""
        notify_patch_plan_generated(
            chat_message_id=self.user_msg.pk,
            upload_id=self.upload.pk,
            prompt="없는 텍스트 교체",
            result=_MOCK_EMPTY_PATCH_PLAN,
        )

        assistant_msg = ChatMessage.objects.filter(
            session=self.session,
            role=ChatMessage.Role.ASSISTANT,
        ).last()

        self.assertIsNotNone(assistant_msg)
        self.assertTrue(assistant_msg.has_snippet, "빈 결과도 완료 마커가 있어야 한다")
        self.assertEqual(assistant_msg.snippet_data.get("type"), "patch_plan")
        self.assertIsNone(assistant_msg.snippet_data.get("version_id"))
        self.assertEqual(assistant_msg.snippet_data.get("changes"), [])
        self.assertEqual(assistant_msg.snippet_data.get("plan_id"), "plan_empty_intent_001")

    def test_empty_patch_plan_message_uses_llm_specific_summary(self):
        """
        [버그 수정] operations=[]일 때 LLM이 생성한 구체적 사유(summary)를 그대로
        채팅 메시지로 보여줘야 한다. 기존에는 이 summary를 버리고 뻔한 안내문으로
        덮어써서, 25초 걸린 LLM의 상세 판단 근거가 사용자에게 전혀 전달되지 않았다.
        """
        detailed_summary = (
            "문서 내 '동의' 문구를 '미동의'로 일괄 교체하는 요청이나, "
            "'동의'가 여러 문맥에서 반복 등장해 위치를 특정할 수 없음"
        )
        notify_patch_plan_generated(
            chat_message_id=self.user_msg.pk,
            upload_id=self.upload.pk,
            prompt="동의를 미동의로 바꿔줘",
            result={**_MOCK_EMPTY_PATCH_PLAN, "summary": detailed_summary},
        )

        assistant_msg = ChatMessage.objects.filter(
            session=self.session, role=ChatMessage.Role.ASSISTANT,
        ).last()
        self.assertEqual(assistant_msg.content, detailed_summary)

    def test_empty_patch_plan_without_summary_falls_back_to_generic_message(self):
        """[회귀] summary가 비어 있으면 기존의 일반 안내 문구로 폴백한다."""
        notify_patch_plan_generated(
            chat_message_id=self.user_msg.pk,
            upload_id=self.upload.pk,
            prompt="없는 텍스트 교체",
            result={**_MOCK_EMPTY_PATCH_PLAN, "summary": ""},
        )

        assistant_msg = ChatMessage.objects.filter(
            session=self.session, role=ChatMessage.Role.ASSISTANT,
        ).last()
        self.assertEqual(
            assistant_msg.content,
            "요청하신 내용에 해당하는 수정 항목을 찾지 못했습니다. 더 구체적인 내용으로 다시 요청해 주세요.",
        )

    @patch("apps.chat.tasks.current_app.send_task", side_effect=RuntimeError("redis down"))
    def test_patch_intent_enqueue_failure_creates_error_message(self, _mock_send_task):
        """ax-engine enqueue 실패 시 태스크 예외 대신 오류 어시스턴트 메시지를 남긴다."""
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
        self.assertIsNotNone(assistant_msg)
        self.assertIn("시작하지 못했습니다", assistant_msg.content)


# ── 의도 분류 사용량 기록 ───────────────────────────────────────────────────────

@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class ChatIntentClassificationUsageEventTest(TestCase):
    """
    upload_id 있는 채팅 요청은 ax-engine이 의도 분류 LLM 호출을 수행한다.
    patch_intent로 분기되는 경우, 해당 LLM 호출의 사용량이 누락되지 않고
    INTENT_CLASSIFICATION 이벤트로 기록되어야 한다.
    """

    def setUp(self):
        self.user = _make_user("intent_usage_user")
        self.session = _make_session(self.user)
        self.upload = _make_done_upload(self.user)
        self.user_msg = _make_user_message(self.session, upload_log=self.upload)

    @patch("apps.chat.tasks.current_app.send_task")
    def test_patch_intent_records_intent_classification_usage_event(self, _mock_send_task):
        """patch_intent 분기에서도 의도 분류 호출의 UsageEvent가 기록된다."""
        result = {
            "type": "patch_intent",
            "refined_prompt": "A2 셀 날짜를 2026-01-01로 교체",
            "upload_id": self.upload.pk,
            "summary": "",
            "errors": [],
            "source_type": "chat",
            "model_used": "claude-sonnet-4-6",
        }

        notify_chat_response(self.user_msg.pk, result)

        event = UsageEvent.objects.filter(
            user=self.user,
            event_type=UsageEvent.EventType.INTENT_CLASSIFICATION,
        ).first()
        self.assertIsNotNone(event, "patch_intent 분기에서도 의도 분류 UsageEvent가 기록되어야 한다")
        self.assertEqual(event.upload_log_id, self.upload.pk)
        self.assertEqual(event.chat_session_id, self.session.pk)


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

    def test_qa_type_sets_snippet_data_type_qa(self):
        """type='qa' 응답은 snippet_data.type='qa'로 저장되어 프론트 폴링 종료 마커를 제공한다."""
        result = {
            "type": "qa",
            "reply": "이 파일은 매출 데이터 Excel 파일입니다.",
            "summary": "이 파일은 매출 데이터 Excel 파일입니다.",
            "errors": [],
            "source_type": "chat",
        }

        notify_chat_response(self.user_msg.pk, result)

        assistant_msg = ChatMessage.objects.filter(
            session=self.session,
            role=ChatMessage.Role.ASSISTANT,
        ).last()
        self.assertIsNotNone(assistant_msg)
        self.assertTrue(assistant_msg.has_snippet, "has_snippet=True이어야 한다")
        self.assertEqual(
            (assistant_msg.snippet_data or {}).get("type"),
            "qa",
            "snippet_data.type이 'qa'이어야 프론트가 폴링을 종료할 수 있다",
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

    def test_no_type_result_sets_snippet_data_type_qa(self):
        """type 필드 없는 순수 텍스트 응답도 snippet_data.type='qa'로 저장된다."""
        result = {
            # type 필드 없음 — 기존 notify_chat_response 형식
            "summary": "Q&A 응답입니다.",
            "errors": [],
            "source_type": "chat",
        }

        notify_chat_response(self.user_msg.pk, result)

        assistant_msg = ChatMessage.objects.filter(
            session=self.session,
            role=ChatMessage.Role.ASSISTANT,
        ).last()
        self.assertIsNotNone(assistant_msg)
        self.assertTrue(assistant_msg.has_snippet, "has_snippet=True이어야 한다")
        self.assertEqual(
            (assistant_msg.snippet_data or {}).get("type"),
            "qa",
            "type 없는 텍스트 응답도 snippet_data.type='qa'이어야 프론트가 폴링을 종료할 수 있다",
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
