"""
RAG 자산 API 테스트.

커버 범위:
  1. GET /api/v1/rag-assets/ — 본인 자산 목록 조회
  2. POST /api/v1/rag-assets/ — 파일 업로드로 자산 생성
  3. DELETE /api/v1/rag-assets/{id}/ — 자산 삭제
  4. 다른 유저 자산 접근 차단 검증
  5. 인증 없이 접근 시 401 반환
  6. kind choices 검증 (tone / form 만 허용)
  7. 파일 업로드 후 trained=False 기본값 검증
"""
import io

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

User = get_user_model()


def _make_user(username="rag_tester"):
    return User.objects.create_user(username=username, password="pw")


def _authed_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _dummy_file(name="sample.txt", content=b"dummy rag file"):
    return SimpleUploadedFile(name, content, content_type="text/plain")


class RagAssetListCreateTest(TestCase):
    """GET / POST /api/v1/rag-assets/ 테스트."""

    def setUp(self):
        self.user = _make_user()
        self.client = _authed_client(self.user)

    def test_empty_list(self):
        """자산이 없으면 빈 배열 반환."""
        response = self.client.get("/api/v1/rag-assets/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_create_tone_asset(self):
        """tone 종류 자산 파일 업로드 생성."""
        response = self.client.post(
            "/api/v1/rag-assets/",
            {
                "kind": "tone",
                "group_name": "하람_보고서_스타일",
                "file": _dummy_file("style.txt"),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["kind"], "tone")
        self.assertEqual(response.data["group_name"], "하람_보고서_스타일")
        self.assertFalse(response.data["trained"])  # 초기값 False
        self.assertGreater(response.data["file_size"], 0)

    def test_create_form_asset(self):
        """form 종류 자산 파일 업로드 생성."""
        response = self.client.post(
            "/api/v1/rag-assets/",
            {
                "kind": "form",
                "group_name": "표준_계약서_양식",
                "file": _dummy_file("form.docx", b"docx content" * 10),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["kind"], "form")

    def test_create_invalid_kind(self):
        """지원하지 않는 kind 값이면 400 반환."""
        response = self.client.post(
            "/api/v1/rag-assets/",
            {
                "kind": "invalid",
                "group_name": "잘못된 종류",
                "file": _dummy_file(),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)

    def test_list_shows_only_own_assets(self):
        """다른 유저의 자산은 목록에 포함되지 않는다."""
        other_client = _authed_client(_make_user(username="rag_other"))
        other_client.post(
            "/api/v1/rag-assets/",
            {"kind": "tone", "group_name": "타인 자산", "file": _dummy_file("other.txt")},
            format="multipart",
        )

        self.client.post(
            "/api/v1/rag-assets/",
            {"kind": "form", "group_name": "내 자산", "file": _dummy_file("mine.txt")},
            format="multipart",
        )

        response = self.client.get("/api/v1/rag-assets/")
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["group_name"], "내 자산")

    def test_unauthenticated_returns_401(self):
        """인증 없이 접근 시 401 반환."""
        response = APIClient().get("/api/v1/rag-assets/")
        self.assertEqual(response.status_code, 401)

    def test_file_required(self):
        """file 없이 POST 시 400 반환."""
        response = self.client.post(
            "/api/v1/rag-assets/",
            {"kind": "tone", "group_name": "파일없음"},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)


class RagAssetDeleteTest(TestCase):
    """DELETE /api/v1/rag-assets/{id}/ 테스트."""

    def setUp(self):
        self.user = _make_user(username="rag_del")
        self.client = _authed_client(self.user)
        res = self.client.post(
            "/api/v1/rag-assets/",
            {
                "kind": "tone",
                "group_name": "삭제할 자산",
                "file": _dummy_file("del.txt"),
            },
            format="multipart",
        )
        self.asset_id = res.data["id"]

    def test_delete_asset(self):
        """DELETE 후 목록에서 제거 확인."""
        del_resp = self.client.delete(f"/api/v1/rag-assets/{self.asset_id}/")
        self.assertEqual(del_resp.status_code, 204)
        list_resp = self.client.get("/api/v1/rag-assets/")
        self.assertEqual(len(list_resp.data), 0)

    def test_other_user_cannot_delete(self):
        """다른 유저는 삭제 불가 (404)."""
        other_client = _authed_client(_make_user(username="rag_stranger"))
        response = other_client.delete(f"/api/v1/rag-assets/{self.asset_id}/")
        self.assertEqual(response.status_code, 404)
