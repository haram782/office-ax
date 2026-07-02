"""
UsageEvent / record_usage_event 테스트.

커버 범위:
  1. record_usage_event 생성 — FK 객체 전달 시 정상 저장
  2. best-effort 실패 처리 — DB 저장이 예외를 던져도 원래 흐름을 깨지 않고 None 반환
  3. 이번 달 / 본인 필터링 — 대시보드 집계 대상 범위 검증
  4. token_source 판별 — provider_reported / unavailable
"""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.documents.models import FileStructure, UploadLog, UsageEvent
from apps.documents.services.usage import record_usage_event, usage_metadata_from_result

User = get_user_model()


def _make_user(username="usage_tester"):
    return User.objects.create_user(username=username, password="pw")


def _make_upload_log(user):
    fs, _ = FileStructure.objects.get_or_create(
        hash="usage_event_hash",
        defaults={"source_type": FileStructure.SourceType.EXCEL, "column_schema": []},
    )
    return UploadLog.objects.create(
        user=user,
        file_structure=fs,
        original_filename="report.xlsx",
        status=UploadLog.Status.DONE,
    )


class RecordUsageEventCreationTest(TestCase):
    """record_usage_event가 FK 객체만으로 UsageEvent를 정상 생성하는지 검증."""

    def setUp(self):
        self.user = _make_user()
        self.upload_log = _make_upload_log(self.user)

    def test_creates_usage_event_with_fk_objects_only(self):
        """user/upload_log FK 객체만 넘겨도 이벤트가 생성된다 (id kwargs 아님)."""
        event = record_usage_event(
            user=self.user,
            upload_log=self.upload_log,
            event_type=UsageEvent.EventType.DOCUMENT_ANALYSIS,
            status=UsageEvent.Status.SUCCESS,
            metadata={"source": "test"},
        )

        self.assertIsNotNone(event)
        self.assertEqual(UsageEvent.objects.count(), 1)
        saved = UsageEvent.objects.get()
        self.assertEqual(saved.user_id, self.user.pk)
        self.assertEqual(saved.upload_log_id, self.upload_log.pk)
        self.assertEqual(saved.event_type, UsageEvent.EventType.DOCUMENT_ANALYSIS)
        self.assertEqual(saved.status, UsageEvent.Status.SUCCESS)

    def test_total_tokens_property(self):
        """total_tokens는 input_tokens + output_tokens를 반환한다."""
        event = record_usage_event(
            user=self.user,
            event_type=UsageEvent.EventType.CHAT_QA,
            input_tokens=120,
            output_tokens=80,
        )
        self.assertEqual(event.total_tokens, 200)


class RecordUsageEventFailureTest(TestCase):
    """DB 저장 실패 시 best-effort로 None을 반환하고 예외를 전파하지 않는지 검증."""

    def setUp(self):
        self.user = _make_user()

    def test_db_error_returns_none_without_raising(self):
        """UsageEvent.objects.create가 예외를 던져도 record_usage_event는 조용히 None을 반환한다."""
        with patch(
            "apps.documents.services.usage.UsageEvent.objects.create",
            side_effect=Exception("db down"),
        ):
            result = record_usage_event(
                user=self.user,
                event_type=UsageEvent.EventType.DOCUMENT_ANALYSIS,
                status=UsageEvent.Status.SUCCESS,
            )
        self.assertIsNone(result)
        self.assertEqual(UsageEvent.objects.count(), 0)

    def test_malformed_metadata_does_not_raise(self):
        """estimated_cost 등 파싱 불가능한 값이 들어와도 예외 없이 기본값으로 저장된다."""
        event = record_usage_event(
            user=self.user,
            event_type=UsageEvent.EventType.PATCH_PLAN_GENERATION,
            estimated_cost="not-a-number",
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.estimated_cost, Decimal("0"))


class UsageEventFilteringTest(TestCase):
    """월별 / 유저별 필터링 검증 — 대시보드 집계 범위와 동일한 조건."""

    def setUp(self):
        self.user = _make_user("filter_user")
        self.other_user = _make_user("filter_other")

    def _current_month_qs(self, user):
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return UsageEvent.objects.filter(user=user, created_at__gte=month_start)

    def test_only_current_user_events_included(self):
        """다른 유저의 이벤트는 필터 결과에 포함되지 않는다."""
        record_usage_event(user=self.user, event_type=UsageEvent.EventType.CHAT_QA)
        record_usage_event(user=self.other_user, event_type=UsageEvent.EventType.CHAT_QA)

        qs = self._current_month_qs(self.user)
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first().user_id, self.user.pk)

    def test_previous_month_events_excluded(self):
        """지난 달 생성된 이벤트는 이번 달 집계에서 제외된다."""
        event = record_usage_event(user=self.user, event_type=UsageEvent.EventType.CHAT_QA)
        # created_at은 auto_now_add라서 직접 update로 과거 시점으로 이동시킨다.
        past = timezone.now() - timedelta(days=45)
        UsageEvent.objects.filter(pk=event.pk).update(created_at=past)

        qs = self._current_month_qs(self.user)
        self.assertEqual(qs.count(), 0)

    def test_current_month_events_included(self):
        """이번 달 생성된 이벤트는 집계에 포함된다."""
        record_usage_event(user=self.user, event_type=UsageEvent.EventType.CHAT_QA)
        qs = self._current_month_qs(self.user)
        self.assertEqual(qs.count(), 1)


class TokenSourceTest(TestCase):
    """token_source 판별 로직 검증."""

    def setUp(self):
        self.user = _make_user("token_source_user")

    def test_defaults_to_unavailable_without_token_counts(self):
        """토큰 수치가 전혀 없으면 token_source는 UNAVAILABLE."""
        event = record_usage_event(
            user=self.user,
            event_type=UsageEvent.EventType.CHAT_QA,
        )
        self.assertEqual(event.token_source, UsageEvent.TokenSource.UNAVAILABLE)

    def test_provider_reported_when_tokens_present(self):
        """usage 메타데이터에 토큰 수치가 있으면 PROVIDER_REPORTED로 추론된다."""
        event = record_usage_event(
            user=self.user,
            event_type=UsageEvent.EventType.CHAT_QA,
            metadata={"usage": {"input_tokens": 100, "output_tokens": 50}},
        )
        self.assertEqual(event.token_source, UsageEvent.TokenSource.PROVIDER_REPORTED)
        self.assertEqual(event.input_tokens, 100)
        self.assertEqual(event.output_tokens, 50)

    def test_explicit_token_source_overrides_inference(self):
        """token_source가 명시적으로 전달되면 추론값보다 우선한다."""
        event = record_usage_event(
            user=self.user,
            event_type=UsageEvent.EventType.CHAT_QA,
            token_source=UsageEvent.TokenSource.ESTIMATED,
            input_tokens=10,
        )
        self.assertEqual(event.token_source, UsageEvent.TokenSource.ESTIMATED)


class UsageMetadataFromResultTest(TestCase):
    """usage_metadata_from_result 헬퍼 검증."""

    def test_extracts_expected_keys_from_result_dict(self):
        result = {
            "provider": "openai",
            "model": "gpt-x",
            "usage": {"input_tokens": 10, "output_tokens": 5},
            "latency_ms": 200,
            "estimated_cost": "1.5",
        }
        metadata = usage_metadata_from_result(result, source="unit_test")
        self.assertEqual(metadata["provider"], "openai")
        self.assertEqual(metadata["model"], "gpt-x")
        self.assertEqual(metadata["usage"], {"input_tokens": 10, "output_tokens": 5})
        self.assertEqual(metadata["source"], "unit_test")

    def test_handles_non_dict_result(self):
        """result가 dict가 아니어도 예외 없이 빈 메타데이터를 반환한다."""
        metadata = usage_metadata_from_result(None, source="unit_test")
        self.assertEqual(metadata["provider"], "")
        self.assertEqual(metadata["source"], "unit_test")
