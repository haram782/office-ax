"""
Dashboard 통계 API 테스트.

커버 범위:
  1. GET /api/v1/dashboard/stats/ — 통계 응답 필드 검증
  2. monthly_processed / monthly_errors / monthly_corrected 집계 검증
  3. 인증 없이 접근 시 401 반환
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.documents.models import FileStructure, UploadLog

User = get_user_model()


def _make_user(username="dash_tester"):
    return User.objects.create_user(username=username, password="pw")


def _authed_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _make_upload_log(user, status):
    fs, _ = FileStructure.objects.get_or_create(
        hash="dash_hash",
        defaults={"source_type": FileStructure.SourceType.EXCEL, "column_schema": []},
    )
    return UploadLog.objects.create(
        user=user,
        file_structure=fs,
        original_filename="report.xlsx",
        status=status,
    )


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
        """응답에 명세된 8개 필드가 모두 존재해야 한다."""
        response = self.client.get("/api/v1/dashboard/stats/")
        self.assertEqual(response.status_code, 200)
        required_fields = [
            "token_used", "token_total", "balance", "deposit",
            "monthly_spent", "monthly_processed", "monthly_errors", "monthly_corrected",
        ]
        for field in required_fields:
            self.assertIn(field, response.data, f"{field} 필드가 응답에 없습니다")

    def test_monthly_processed_counts_done_uploads(self):
        """이번 달 DONE 상태 업로드 수가 monthly_processed에 반영된다."""
        _make_upload_log(self.user, UploadLog.Status.DONE)
        _make_upload_log(self.user, UploadLog.Status.DONE)
        _make_upload_log(self.user, UploadLog.Status.FAILED)  # 오류 건

        response = self.client.get("/api/v1/dashboard/stats/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["monthly_processed"], 2)
        self.assertEqual(response.data["monthly_errors"], 1)

    def test_monthly_corrected_equals_processed_minus_errors(self):
        """monthly_corrected = monthly_processed - monthly_errors."""
        _make_upload_log(self.user, UploadLog.Status.DONE)
        _make_upload_log(self.user, UploadLog.Status.DONE)
        _make_upload_log(self.user, UploadLog.Status.DONE)
        _make_upload_log(self.user, UploadLog.Status.FAILED)

        response = self.client.get("/api/v1/dashboard/stats/")
        processed = response.data["monthly_processed"]
        errors = response.data["monthly_errors"]
        corrected = response.data["monthly_corrected"]
        self.assertEqual(corrected, processed - errors)

    def test_other_user_stats_not_included(self):
        """다른 유저의 업로드 이력은 통계에 포함되지 않는다."""
        other = _make_user(username="dash_other")
        # 다른 유저의 완료 로그 5건 생성
        for _ in range(5):
            _make_upload_log(other, UploadLog.Status.DONE)

        # 내 업로드: 1건만
        _make_upload_log(self.user, UploadLog.Status.DONE)

        response = self.client.get("/api/v1/dashboard/stats/")
        self.assertEqual(response.data["monthly_processed"], 1)

    def test_all_fields_are_integers(self):
        """모든 응답 필드 값이 정수형이어야 한다."""
        response = self.client.get("/api/v1/dashboard/stats/")
        for field in ["token_used", "token_total", "balance", "deposit",
                      "monthly_spent", "monthly_processed", "monthly_errors", "monthly_corrected"]:
            self.assertIsInstance(response.data[field], int, f"{field}가 정수가 아닙니다")
