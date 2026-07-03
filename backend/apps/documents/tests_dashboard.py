"""
Dashboard 통계 API 테스트.

커버 범위:
  1. GET /api/v1/dashboard/stats/ — 통계 응답 필드 검증
  2. UsageEvent 기반 monthly_processed / monthly_errors / monthly_corrected 집계 검증
  3. 인증 없이 접근 시 401 반환
  4. 본인 / 이번 달 UsageEvent만 집계에 포함되는지 검증
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.documents.models import DocumentVersion, FileStructure, UploadLog, UsageEvent

User = get_user_model()


def _make_user(username="dash_tester"):
    return User.objects.create_user(username=username, password="pw")


def _authed_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _make_upload_log(user):
    fs, _ = FileStructure.objects.get_or_create(
        hash="dash_hash",
        defaults={"source_type": FileStructure.SourceType.EXCEL, "column_schema": []},
    )
    return UploadLog.objects.create(
        user=user,
        file_structure=fs,
        original_filename="report.xlsx",
        status=UploadLog.Status.DONE,
    )


def _make_document_version(upload_log, user):
    return DocumentVersion.objects.create(
        upload_log=upload_log,
        created_by=user,
        status=DocumentVersion.Status.READY,
    )


def _make_usage_event(user, event_type, status, upload_log=None, document_version=None, created_at=None):
    event = UsageEvent.objects.create(
        user=user,
        upload_log=upload_log,
        document_version=document_version,
        event_type=event_type,
        status=status,
    )
    if created_at is not None:
        UsageEvent.objects.filter(pk=event.pk).update(created_at=created_at)
    return event


class DashboardStatsTest(TestCase):
    """GET /api/v1/dashboard/stats/ 테스트."""

    def setUp(self):
        self.user = _make_user()
        self.client = _authed_client(self.user)

    def test_unauthenticated_returns_401(self):
        """인증 없이 접근 시 401 반환."""
        response = APIClient().get("/api/v1/dashboard/stats/")
        self.assertEqual(response.status_code, 401)

    def test_response_has_required_fields(self):
        """응답에 명세된 8개 레거시 호환 필드가 모두 존재해야 한다."""
        response = self.client.get("/api/v1/dashboard/stats/")
        self.assertEqual(response.status_code, 200)
        required_fields = [
            "token_used", "token_total", "balance", "deposit",
            "monthly_spent", "monthly_processed", "monthly_errors", "monthly_corrected",
        ]
        for field in required_fields:
            self.assertIn(field, response.data, f"{field} 필드가 응답에 없습니다")

    def test_monthly_processed_counts_successful_analysis_events(self):
        """이번 달 DOCUMENT_ANALYSIS 성공 UsageEvent 수가 monthly_processed에 반영된다."""
        upload_log_1 = _make_upload_log(self.user)
        upload_log_2 = _make_upload_log(self.user)
        upload_log_3 = _make_upload_log(self.user)
        _make_usage_event(self.user, UsageEvent.EventType.DOCUMENT_ANALYSIS, UsageEvent.Status.SUCCESS, upload_log_1)
        _make_usage_event(self.user, UsageEvent.EventType.DOCUMENT_ANALYSIS, UsageEvent.Status.SUCCESS, upload_log_2)
        _make_usage_event(self.user, UsageEvent.EventType.DOCUMENT_ANALYSIS, UsageEvent.Status.FAILED, upload_log_3)

        response = self.client.get("/api/v1/dashboard/stats/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["monthly_processed"], 2)
        self.assertEqual(response.data["monthly_errors"], 1)

    def test_monthly_corrected_counts_successful_patch_artifact_events(self):
        """monthly_corrected는 PATCH_ARTIFACT_GENERATION 성공 이벤트(고유 버전) 수를 반영한다."""
        upload_log = _make_upload_log(self.user)
        version_1 = _make_document_version(upload_log, self.user)
        version_2 = _make_document_version(upload_log, self.user)

        _make_usage_event(
            self.user, UsageEvent.EventType.PATCH_ARTIFACT_GENERATION, UsageEvent.Status.SUCCESS,
            upload_log, version_1,
        )
        _make_usage_event(
            self.user, UsageEvent.EventType.PATCH_ARTIFACT_GENERATION, UsageEvent.Status.SUCCESS,
            upload_log, version_2,
        )
        _make_usage_event(
            self.user, UsageEvent.EventType.PATCH_ARTIFACT_GENERATION, UsageEvent.Status.FAILED,
            upload_log, None,
        )

        response = self.client.get("/api/v1/dashboard/stats/")
        self.assertEqual(response.data["monthly_corrected"], 2)
        self.assertEqual(response.data["failed_jobs"], 1)

    def test_other_user_stats_not_included(self):
        """다른 유저의 UsageEvent는 통계에 포함되지 않는다."""
        other = _make_user(username="dash_other")
        other_upload = _make_upload_log(other)
        for _ in range(5):
            _make_usage_event(other, UsageEvent.EventType.DOCUMENT_ANALYSIS, UsageEvent.Status.SUCCESS, other_upload)

        my_upload = _make_upload_log(self.user)
        _make_usage_event(self.user, UsageEvent.EventType.DOCUMENT_ANALYSIS, UsageEvent.Status.SUCCESS, my_upload)

        response = self.client.get("/api/v1/dashboard/stats/")
        self.assertEqual(response.data["monthly_processed"], 1)

    def test_previous_month_events_excluded_from_stats(self):
        """지난 달 UsageEvent는 이번 달 통계에서 제외된다."""
        upload_log = _make_upload_log(self.user)
        past = timezone.now() - timedelta(days=45)
        _make_usage_event(
            self.user, UsageEvent.EventType.DOCUMENT_ANALYSIS, UsageEvent.Status.SUCCESS,
            upload_log, created_at=past,
        )

        response = self.client.get("/api/v1/dashboard/stats/")
        self.assertEqual(response.data["monthly_processed"], 0)
        self.assertEqual(response.data["ai_calls"], 0)

    def test_token_source_counts_present_in_response(self):
        """token_source_counts는 UsageEvent.TokenSource 각 선택지를 키로 포함한다."""
        record_kwargs = dict(user=self.user, event_type=UsageEvent.EventType.CHAT_QA, status=UsageEvent.Status.SUCCESS)
        UsageEvent.objects.create(token_source=UsageEvent.TokenSource.PROVIDER_REPORTED, **record_kwargs)
        UsageEvent.objects.create(token_source=UsageEvent.TokenSource.UNAVAILABLE, **record_kwargs)

        response = self.client.get("/api/v1/dashboard/stats/")
        counts = response.data["token_source_counts"]
        self.assertEqual(counts[UsageEvent.TokenSource.PROVIDER_REPORTED], 1)
        self.assertEqual(counts[UsageEvent.TokenSource.UNAVAILABLE], 1)
        self.assertEqual(counts[UsageEvent.TokenSource.ESTIMATED], 0)

    def test_all_legacy_fields_are_integers(self):
        """모든 레거시 호환 필드 값이 정수형이어야 한다."""
        response = self.client.get("/api/v1/dashboard/stats/")
        for field in ["token_used", "token_total", "balance", "deposit",
                      "monthly_spent", "monthly_processed", "monthly_errors", "monthly_corrected"]:
            self.assertIsInstance(response.data[field], int, f"{field}가 정수가 아닙니다")
