"""
클로즈드 베타 월간 크레딧 하드 한도 테스트.

closed-beta-launch-plan-v1-ko.md 2.2절 결정 16 / 6절 기준:
  - 비싼 endpoint 4곳(업로드·채팅 전송·PatchPlan 생성·patch 실행)은
    이번 달 크레딧 소진 시 429를 반환한다
  - 크레딧 차감 대상: document_analysis, patch_plan_generation, patch_artifact_generation
  - 실패(FAILED) 이벤트는 차감하지 않는다
  - BETA_MONTHLY_CREDITS 미설정 시 기본 200, 0 이하면 무제한

Red → Green → Refactor
"""
import io
import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.chat.models import ChatSession
from apps.documents.models import UsageEvent
from apps.documents.services.usage import record_usage_event

User = get_user_model()


def _make_client(username="credit_user"):
    """인증된 APIClient와 유저를 만든다."""
    user = User.objects.create_user(username=username, email=f"{username}@test.com")
    token, _ = Token.objects.get_or_create(user=user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client, user


def _seed_events(user, count, *, event_type=UsageEvent.EventType.DOCUMENT_ANALYSIS,
                 status=UsageEvent.Status.SUCCESS):
    """이번 달 UsageEvent를 count개 적재한다."""
    for _ in range(count):
        record_usage_event(user=user, event_type=event_type, status=status)


def _fake_xlsx():
    """업로드용 최소 XLSX — 업로드 뷰가 openpyxl로 파일을 열기 때문에 실제 워크북이 필요하다."""
    from openpyxl import Workbook

    wb = Workbook()
    wb.active["A1"] = "값"
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    buf.name = "report.xlsx"
    return buf


class CreditLimitBlocksEndpointsTest(TestCase):
    """한도 소진 시 비싼 endpoint 4곳이 429를 반환하는지 검증."""

    def setUp(self):
        self.client, self.user = _make_client()

    def _exhaust_credits(self, limit=2):
        _seed_events(self.user, limit)
        return patch.dict(os.environ, {"BETA_MONTHLY_CREDITS": str(limit)})

    def test_upload_returns_429_when_exhausted(self):
        """[실패 케이스] 업로드 생성은 한도 소진 시 429 + 안내 문구를 반환한다."""
        with self._exhaust_credits():
            response = self.client.post("/api/v1/uploads/", {"file": _fake_xlsx()}, format="multipart")
        self.assertEqual(response.status_code, 429)
        self.assertIn("사용량", str(response.data))

    def test_upload_429_leaves_no_upload_log(self):
        """차단된 업로드는 UploadLog 레코드를 남기지 않아야 한다."""
        from apps.documents.models import UploadLog
        with self._exhaust_credits():
            self.client.post("/api/v1/uploads/", {"file": _fake_xlsx()}, format="multipart")
        self.assertEqual(UploadLog.objects.filter(user=self.user).count(), 0)

    def test_chat_send_returns_429_when_exhausted(self):
        """채팅 메시지 전송도 한도 소진 시 429 (LLM 폭주 방어)."""
        session = ChatSession.objects.create(user=self.user, title="테스트 세션")
        with self._exhaust_credits():
            response = self.client.post(
                f"/api/v1/chat/sessions/{session.pk}/messages/send/",
                {"content": "안녕"},
                format="json",
            )
        self.assertEqual(response.status_code, 429)

    def test_generate_patch_plan_returns_429_when_exhausted(self):
        """PatchPlan 생성은 한도 체크가 소유권 조회보다 먼저 수행된다."""
        with self._exhaust_credits():
            response = self.client.post("/api/v1/uploads/999/generate-patch-plan/", {}, format="json")
        self.assertEqual(response.status_code, 429)

    def test_patch_trigger_returns_429_when_exhausted(self):
        """patch 실행도 한도 소진 시 429."""
        with self._exhaust_credits():
            response = self.client.post("/api/v1/uploads/999/versions/999/patch/", {}, format="json")
        self.assertEqual(response.status_code, 429)


class CreditCountingRuleTest(TestCase):
    """크레딧 카운팅 규칙 검증 — endpoint 동작으로 표현한다."""

    def setUp(self):
        self.client, self.user = _make_client()

    def _post_upload(self):
        # 한도 통과 시 업로드는 태스크 예약까지 진행되므로 send_task는 목 처리
        with patch("apps.documents.views.current_app.send_task") as mock_task:
            mock_task.return_value.id = "task-credit-test"
            return self.client.post("/api/v1/uploads/", {"file": _fake_xlsx()}, format="multipart")

    def test_under_limit_allows_request(self):
        """[happy] 한도 미만이면 요청이 429로 차단되지 않는다."""
        _seed_events(self.user, 1)
        with patch.dict(os.environ, {"BETA_MONTHLY_CREDITS": "2"}):
            response = self._post_upload()
        self.assertNotEqual(response.status_code, 429)

    def test_failed_events_do_not_consume_credits(self):
        """[규칙] 실패한 LLM 호출은 크레딧을 차감하지 않는다."""
        _seed_events(self.user, 2, status=UsageEvent.Status.FAILED)
        with patch.dict(os.environ, {"BETA_MONTHLY_CREDITS": "2"}):
            response = self._post_upload()
        self.assertNotEqual(response.status_code, 429)

    def test_non_credit_event_types_do_not_consume(self):
        """[규칙] chat_qa·intent_classification은 크레딧 차감 대상이 아니다."""
        _seed_events(self.user, 2, event_type=UsageEvent.EventType.CHAT_QA)
        _seed_events(self.user, 2, event_type=UsageEvent.EventType.INTENT_CLASSIFICATION)
        with patch.dict(os.environ, {"BETA_MONTHLY_CREDITS": "2"}):
            response = self._post_upload()
        self.assertNotEqual(response.status_code, 429)

    def test_other_users_events_do_not_consume(self):
        """[규칙] 다른 유저의 사용량은 내 크레딧에 영향이 없다."""
        _, other = _make_client(username="other_user")
        _seed_events(other, 5)
        with patch.dict(os.environ, {"BETA_MONTHLY_CREDITS": "2"}):
            response = self._post_upload()
        self.assertNotEqual(response.status_code, 429)

    def test_last_month_events_do_not_consume(self):
        """[경계] 지난달 이벤트는 이번 달 크레딧에서 제외된다."""
        from datetime import timedelta
        from django.utils import timezone

        _seed_events(self.user, 2)
        # created_at은 auto_now_add이므로 생성 후 지난달로 강제 이동
        UsageEvent.objects.filter(user=self.user).update(
            created_at=timezone.now().replace(day=1) - timedelta(days=1)
        )
        with patch.dict(os.environ, {"BETA_MONTHLY_CREDITS": "2"}):
            response = self._post_upload()
        self.assertNotEqual(response.status_code, 429)

    def test_zero_limit_means_unlimited(self):
        """[경계] BETA_MONTHLY_CREDITS=0은 무제한으로 취급한다 (운영 편의)."""
        _seed_events(self.user, 5)
        with patch.dict(os.environ, {"BETA_MONTHLY_CREDITS": "0"}):
            response = self._post_upload()
        self.assertNotEqual(response.status_code, 429)
