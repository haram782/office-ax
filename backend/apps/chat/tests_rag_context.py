"""
채팅 RAG 자산 컨텍스트 전달 테스트 (점검 발견 A-2).

기존: RagSelector 선택이 채팅 API로 전달되지 않아 RAG 기능 전체가 장식.
변경: rag_asset_ids(JSON 배열 문자열)를 받아 소유 자산의 파일 경로를
      text_chat 태스크 kwargs(rag_files)로 넘긴다 — 프롬프트 주입은 ax-engine 담당.

Red → Green → Refactor
"""
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.chat.models import ChatSession
from apps.rag.models import RagAsset

User = get_user_model()


def _make_client(username):
    user = User.objects.create_user(username=username, email=f"{username}@t.co")
    token, _ = Token.objects.get_or_create(user=user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client, user


def _make_asset(owner, kind="tone", group_name="보고서_어투"):
    return RagAsset.objects.create(
        kind=kind,
        group_name=group_name,
        owner=owner,
        file=SimpleUploadedFile("tone_sample.csv", "정중한 보고체 예시".encode()),
    )


class ChatRagContextDispatchTest(TestCase):
    """rag_asset_ids → text_chat kwargs.rag_files 전달 검증."""

    def setUp(self):
        self.client_api, self.user = _make_client("rag_chat_user")
        self.session = ChatSession.objects.create(user=self.user, title="rag 세션")
        self.asset = _make_asset(self.user)
        self.url = f"/api/v1/chat/sessions/{self.session.pk}/messages/send/"

    def _send(self, **extra):
        with patch("apps.chat.views.current_app.send_task") as mock_send:
            mock_send.return_value.id = "task-rag"
            response = self.client_api.post(
                self.url, {"content": "이 어투로 요약해줘", **extra}, format="multipart",
            )
        return response, mock_send

    def test_owned_asset_paths_are_dispatched(self):
        """[happy] 소유 자산 id를 보내면 kind·group_name·파일 경로가 태스크로 전달된다."""
        response, mock_send = self._send(rag_asset_ids=json.dumps([self.asset.pk]))
        self.assertEqual(response.status_code, 202)

        kwargs = mock_send.call_args.kwargs.get("kwargs", {})
        rag_files = kwargs.get("rag_files")
        self.assertIsInstance(rag_files, list)
        self.assertEqual(len(rag_files), 1)
        self.assertEqual(rag_files[0]["kind"], "tone")
        self.assertEqual(rag_files[0]["group_name"], "보고서_어투")
        self.assertTrue(rag_files[0]["path"].endswith(".csv"))

    def test_foreign_asset_ids_are_ignored(self):
        """[안전] 타인 소유 자산 id는 조용히 무시된다."""
        _, other = _make_client("rag_other_user")
        foreign = _make_asset(other, group_name="남의_자산")

        response, mock_send = self._send(
            rag_asset_ids=json.dumps([self.asset.pk, foreign.pk])
        )
        self.assertEqual(response.status_code, 202)

        rag_files = mock_send.call_args.kwargs["kwargs"]["rag_files"]
        self.assertEqual(len(rag_files), 1)
        self.assertEqual(rag_files[0]["group_name"], "보고서_어투")

    def test_malformed_rag_asset_ids_returns_400(self):
        """[검증] JSON 배열이 아닌 값은 400."""
        response, _ = self._send(rag_asset_ids="not-json")
        self.assertEqual(response.status_code, 400)

    def test_without_rag_asset_ids_dispatches_none(self):
        """[회귀] rag_asset_ids 없으면 rag_files는 None으로 기존 동작 유지."""
        response, mock_send = self._send()
        self.assertEqual(response.status_code, 202)
        kwargs = mock_send.call_args.kwargs.get("kwargs", {})
        self.assertIsNone(kwargs.get("rag_files"))
