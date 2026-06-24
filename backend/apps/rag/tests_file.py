"""
RAG 자산 파일 URL 반환 API 테스트.

커버 범위:
  1. GET /api/v1/rag-assets/:id/file/ — 파일 URL 반환
  2. 타인 자산 → 404
  3. 인증 없이 → 401
"""
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from apps.rag.models import RagAsset

User = get_user_model()


def _make_user(username="rag_file_tester"):
    return User.objects.create_user(username=username, password="pw")


def _authed_client(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def _make_asset(user, filename="style.txt"):
    return RagAsset.objects.create(
        kind=RagAsset.Kind.TONE,
        group_name="테스트 어투",
        file=SimpleUploadedFile(filename, b"rag content"),
        file_size=11,
        owner=user,
    )


class RagAssetFileUrlTest(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.client = _authed_client(self.user)
        self.asset = _make_asset(self.user)

    def test_returns_file_url(self):
        """파일이 있으면 file_url을 반환한다."""
        response = self.client.get(f"/api/v1/rag-assets/{self.asset.pk}/file/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("file_url", response.data)
        # 파일명 기반 문자열이 URL에 포함되어야 한다
        # (Django storage는 중복 방지용 접미사를 붙일 수 있으므로 기본 이름만 검증)
        self.assertIn("style", response.data["file_url"])
        self.assertTrue(response.data["file_url"].endswith(".txt"))

    def test_other_user_cannot_access(self):
        """타인의 RAG 자산 파일 URL 조회 불가 (404)."""
        other = _make_user(username="rag_file_other")
        other_asset = _make_asset(other, filename="other.txt")
        response = self.client.get(f"/api/v1/rag-assets/{other_asset.pk}/file/")
        self.assertEqual(response.status_code, 404)

    def test_unauthenticated_returns_401(self):
        """인증 없이 접근 시 401 반환."""
        response = APIClient().get(f"/api/v1/rag-assets/{self.asset.pk}/file/")
        self.assertEqual(response.status_code, 401)
