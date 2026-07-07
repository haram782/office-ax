"""
텍스트 채팅 dispatch 전환 테스트.

검증 대상:
  1. 텍스트 메시지 POST → tasks.text_chat 태스크가 ax 큐로 dispatch됨
  2. dispatch kwargs에 content, chat_message_id, session_history가 포함됨
  3. session_history가 최근 10개 이내 메시지로 제한됨 (최신 기준)
  4. session_history 역할 레이블(role)이 올바르게 매핑됨
  5. 텍스트 분기가 202 + status='processing' 반환
  6. 파일 첨부 메시지 흐름에 영향 없음 (analyze_document 그대로 dispatch)
"""
from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.chat.models import ChatMessage, ChatSession

User = get_user_model()


def _make_user(username="text_chat_tester"):
    return User.objects.create_user(username=username, password="pw")


def _make_session(user):
    return ChatSession.objects.create(user=user, title="텍스트 채팅 테스트")


def _make_message(session, role, content):
    return ChatMessage.objects.create(session=session, role=role, content=content)


class TextChatDispatchTest(TestCase):
    """텍스트 전용 메시지 → text_chat 태스크 dispatch 테스트."""

    def setUp(self):
        self.user = _make_user()
        self.session = _make_session(self.user)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.url = f"/api/v1/chat/sessions/{self.session.pk}/messages/send/"

    def _post_text(self, content="안녕하세요"):
        return self.client.post(self.url, {"content": content}, format="json")

    def test_text_message_returns_202_processing(self):
        """텍스트 메시지 전송 시 202 + status='processing' 반환."""
        with patch("apps.chat.views.current_app.send_task") as mock_send:
            mock_send.return_value = MagicMock(id="fake-task-id")
            response = self._post_text("질문입니다")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["status"], "processing")

    def test_first_text_message_returns_generated_session_title(self):
        """빈 제목 세션의 첫 메시지 응답에는 자동 생성된 session_title이 포함되어야 한다."""
        self.session.title = ""
        self.session.save(update_fields=["title"])

        with patch("apps.chat.views.current_app.send_task") as mock_send:
            mock_send.return_value = MagicMock(id="fake-task-id")
            response = self._post_text("주간 매출 보고서 정리")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["session_title"], "주간 매출 보고서 정리")

    def test_text_message_dispatches_text_chat_task(self):
        """텍스트 메시지 → tasks.text_chat 태스크 이름으로 dispatch."""
        with patch("apps.chat.views.current_app.send_task") as mock_send:
            mock_send.return_value = MagicMock(id="fake-task-id")
            self._post_text("질문입니다")

        mock_send.assert_called_once()
        task_name = mock_send.call_args.args[0]
        self.assertEqual(task_name, "tasks.text_chat")

    def test_text_task_dispatched_to_ax_queue(self):
        """tasks.text_chat는 ax 큐로 dispatch해야 한다."""
        with patch("apps.chat.views.current_app.send_task") as mock_send:
            mock_send.return_value = MagicMock(id="fake-task-id")
            self._post_text("질문")

        call_kwargs = mock_send.call_args.kwargs
        self.assertEqual(call_kwargs.get("queue"), "ax")

    def test_text_task_kwargs_contain_content_and_message_id(self):
        """dispatch kwargs에 content와 chat_message_id가 포함되어야 한다."""
        with patch("apps.chat.views.current_app.send_task") as mock_send:
            mock_send.return_value = MagicMock(id="fake-task-id")
            self._post_text("사용자 메시지")

        dispatched_kwargs = mock_send.call_args.kwargs.get("kwargs", {})
        self.assertEqual(dispatched_kwargs["content"], "사용자 메시지")
        self.assertIn("chat_message_id", dispatched_kwargs)
        # chat_message_id는 방금 생성된 user 메시지 pk
        user_msg = ChatMessage.objects.filter(
            session=self.session, role=ChatMessage.Role.USER
        ).last()
        self.assertEqual(dispatched_kwargs["chat_message_id"], user_msg.pk)

    def test_session_history_included_in_dispatch(self):
        """dispatch kwargs에 session_history가 포함되어야 한다."""
        # 사전 대화 2개 생성
        _make_message(self.session, ChatMessage.Role.USER, "이전 질문")
        _make_message(self.session, ChatMessage.Role.ASSISTANT, "이전 답변")

        with patch("apps.chat.views.current_app.send_task") as mock_send:
            mock_send.return_value = MagicMock(id="fake-task-id")
            self._post_text("새 질문")

        dispatched_kwargs = mock_send.call_args.kwargs.get("kwargs", {})
        history = dispatched_kwargs.get("session_history", [])
        self.assertIsInstance(history, list)
        # 이전 2개 메시지가 history에 있어야 한다 (새 메시지 제외)
        self.assertEqual(len(history), 2)

    def test_session_history_role_mapping(self):
        """session_history의 role이 'user'/'assistant'로 올바르게 매핑되어야 한다."""
        _make_message(self.session, ChatMessage.Role.USER, "사용자 질문")
        _make_message(self.session, ChatMessage.Role.ASSISTANT, "AI 답변")

        with patch("apps.chat.views.current_app.send_task") as mock_send:
            mock_send.return_value = MagicMock(id="fake-task-id")
            self._post_text("새 질문")

        dispatched_kwargs = mock_send.call_args.kwargs.get("kwargs", {})
        history = dispatched_kwargs.get("session_history", [])
        roles = [m["role"] for m in history]
        self.assertIn("user", roles)
        self.assertIn("assistant", roles)

    def test_session_history_limited_to_10(self):
        """session_history는 최근 10개 메시지로 제한되어야 한다."""
        # 12개 메시지 생성 (현재 dispatch될 메시지 제외)
        for i in range(12):
            role = ChatMessage.Role.USER if i % 2 == 0 else ChatMessage.Role.ASSISTANT
            _make_message(self.session, role, f"메시지 {i}")

        with patch("apps.chat.views.current_app.send_task") as mock_send:
            mock_send.return_value = MagicMock(id="fake-task-id")
            self._post_text("신규 질문")

        dispatched_kwargs = mock_send.call_args.kwargs.get("kwargs", {})
        history = dispatched_kwargs.get("session_history", [])
        self.assertLessEqual(len(history), 10)

    def test_session_history_is_chronological(self):
        """session_history는 오래된 것부터 최신순으로 정렬되어야 한다 (정순)."""
        _make_message(self.session, ChatMessage.Role.USER, "첫 번째 메시지")
        _make_message(self.session, ChatMessage.Role.ASSISTANT, "두 번째 메시지")
        _make_message(self.session, ChatMessage.Role.USER, "세 번째 메시지")

        with patch("apps.chat.views.current_app.send_task") as mock_send:
            mock_send.return_value = MagicMock(id="fake-task-id")
            self._post_text("네 번째")

        dispatched_kwargs = mock_send.call_args.kwargs.get("kwargs", {})
        history = dispatched_kwargs.get("session_history", [])
        contents = [m["content"] for m in history]
        self.assertEqual(contents, ["첫 번째 메시지", "두 번째 메시지", "세 번째 메시지"])

    def test_no_static_assistant_message_created(self):
        """텍스트 분기에서 정적 어시스턴트 응답이 생성되지 않아야 한다."""
        with patch("apps.chat.views.current_app.send_task") as mock_send:
            mock_send.return_value = MagicMock(id="fake-task-id")
            self._post_text("질문")

        # ASSISTANT 메시지가 즉시 생성되면 안 됨 (비동기 콜백이 생성함)
        assistant_msgs = ChatMessage.objects.filter(
            session=self.session, role=ChatMessage.Role.ASSISTANT
        )
        self.assertEqual(assistant_msgs.count(), 0)


class FileAttachmentUnaffectedTest(TestCase):
    """파일 첨부 분기가 텍스트 dispatch 변경에 영향 받지 않음 확인."""

    def setUp(self):
        self.user = _make_user(username="file_check_tester")
        self.session = _make_session(self.user)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.url = f"/api/v1/chat/sessions/{self.session.pk}/messages/send/"

    def test_file_attachment_still_dispatches_analyze_document(self):
        """파일 첨부 메시지는 tasks.analyze_document로 dispatch되어야 한다."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        with patch("apps.chat.views.compute_sha256", return_value="newhash123"), \
             patch("apps.chat.views.default_storage.save", return_value="uploads/test.xlsx"), \
             patch("apps.chat.views.os.path.join", return_value="/tmp/test.xlsx"), \
             patch("apps.chat.views.extract_excel_columns", return_value=[]), \
             patch("apps.chat.views.current_app.send_task") as mock_send:

            mock_send.return_value = MagicMock(id="analyze-task-id")
            file = SimpleUploadedFile("test.xlsx", b"fake", content_type="application/vnd.ms-excel")
            response = self.client.post(self.url, {"file": file}, format="multipart")

        self.assertEqual(response.status_code, 202)
        # analyze_document로 dispatch 확인
        task_name = mock_send.call_args.args[0]
        self.assertEqual(task_name, "tasks.analyze_document")
