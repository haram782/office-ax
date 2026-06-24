"""
Conversations API 테스트.

커버 범위:
  1. GET  /api/v1/conversations/              — 본인 세션 목록 (messages 미포함, 경량)
  2. POST /api/v1/conversations/              — 새 세션 생성
  3. GET  /api/v1/conversations/:id/messages/ — 세션 메시지 이력
  4. 타인 세션 메시지 접근 차단
  5. 인증 없이 접근 시 401
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.chat.models import ChatMessage, ChatSession

User = get_user_model()


def _make_user(username="conv_tester"):
    return User.objects.create_user(username=username, password="pw")


def _authed_client(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def _make_session(user, title="테스트 대화"):
    return ChatSession.objects.create(user=user, title=title)


def _add_message(session, role, content):
    return ChatMessage.objects.create(session=session, role=role, content=content)


class ConversationListCreateTest(TestCase):
    """GET / POST /api/v1/conversations/ 테스트."""

    def setUp(self):
        self.user = _make_user()
        self.client = _authed_client(self.user)

    def test_empty_list(self):
        """세션이 없으면 빈 배열 반환."""
        response = self.client.get("/api/v1/conversations/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_create_session(self):
        """새 대화 세션 생성 성공."""
        response = self.client.post(
            "/api/v1/conversations/", {"title": "새 대화"}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["title"], "새 대화")
        self.assertIn("id", response.data)

    def test_create_session_without_title(self):
        """title 없이 생성해도 성공 (빈 문자열 허용)."""
        response = self.client.post("/api/v1/conversations/", {}, format="json")
        self.assertEqual(response.status_code, 201)

    def test_list_shows_only_own_sessions(self):
        """다른 유저의 세션은 목록에 포함되지 않는다."""
        other = _make_user(username="conv_other")
        _make_session(other, title="타인 세션")
        _make_session(self.user, title="내 세션")

        response = self.client.get("/api/v1/conversations/")
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["title"], "내 세션")

    def test_list_does_not_include_messages(self):
        """목록 응답에 messages 배열이 포함되지 않아야 한다 (경량 직렬화)."""
        _make_session(self.user)
        response = self.client.get("/api/v1/conversations/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("messages", response.data[0])

    def test_list_includes_message_count(self):
        """목록 응답에 message_count 필드가 포함되어야 한다."""
        session = _make_session(self.user)
        _add_message(session, ChatMessage.Role.USER, "안녕")
        _add_message(session, ChatMessage.Role.ASSISTANT, "안녕하세요")

        response = self.client.get("/api/v1/conversations/")
        self.assertEqual(response.data[0]["message_count"], 2)

    def test_unauthenticated_returns_401(self):
        """인증 없이 접근 시 401 반환."""
        response = APIClient().get("/api/v1/conversations/")
        self.assertEqual(response.status_code, 401)


class ConversationMessageListTest(TestCase):
    """GET /api/v1/conversations/:id/messages/ 테스트."""

    def setUp(self):
        self.user = _make_user(username="conv_msg")
        self.client = _authed_client(self.user)
        self.session = _make_session(self.user, title="메시지 테스트 세션")
        _add_message(self.session, ChatMessage.Role.USER, "첫 번째 메시지")
        _add_message(self.session, ChatMessage.Role.ASSISTANT, "첫 번째 응답")

    def test_returns_messages_for_own_session(self):
        """본인 세션의 메시지 이력 반환."""
        response = self.client.get(f"/api/v1/conversations/{self.session.pk}/messages/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)
        self.assertEqual(response.data[0]["role"], "user")
        self.assertEqual(response.data[1]["role"], "assistant")

    def test_message_fields(self):
        """응답에 role, content, created_at 등 필수 필드 포함 확인."""
        response = self.client.get(f"/api/v1/conversations/{self.session.pk}/messages/")
        msg = response.data[0]
        for field in ["id", "role", "content", "created_at"]:
            self.assertIn(field, msg, f"{field} 필드가 메시지 응답에 없습니다")

    def test_other_user_cannot_access_messages(self):
        """다른 유저의 세션 메시지에 접근 불가 (404)."""
        other = _make_user(username="conv_stranger")
        other_client = _authed_client(other)
        response = other_client.get(f"/api/v1/conversations/{self.session.pk}/messages/")
        self.assertEqual(response.status_code, 404)

    def test_unauthenticated_returns_401(self):
        """인증 없이 접근 시 401 반환."""
        response = APIClient().get(f"/api/v1/conversations/{self.session.pk}/messages/")
        self.assertEqual(response.status_code, 401)
