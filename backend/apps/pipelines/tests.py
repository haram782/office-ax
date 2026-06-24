"""
Pipeline CRUD API 테스트.

커버 범위:
  1. GET /api/v1/pipelines/ — 목록 조회 (본인 것만)
  2. POST /api/v1/pipelines/ — 생성
  3. GET /api/v1/pipelines/{id}/ — 단건 조회
  4. PATCH /api/v1/pipelines/{id}/ — 부분 수정
  5. DELETE /api/v1/pipelines/{id}/ — 삭제
  6. 다른 유저 파이프라인 접근 차단 검증
  7. 인증 없이 접근 시 401 응답 검증
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

User = get_user_model()


def _make_user(username="pipe_tester"):
    return User.objects.create_user(username=username, password="pw")


def _authed_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


class PipelineListCreateTest(TestCase):
    """GET /api/v1/pipelines/ 및 POST 테스트."""

    def setUp(self):
        self.user = _make_user()
        self.client = _authed_client(self.user)

    def test_empty_list(self):
        """파이프라인이 없으면 빈 배열 반환."""
        response = self.client.get("/api/v1/pipelines/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_create_pipeline(self):
        """파이프라인 생성 성공 — 필수 필드 검증."""
        payload = {
            "name": "테스트 파이프라인",
            "type": "A",
            "trigger_meta": {},
            "is_active": True,
        }
        response = self.client.post("/api/v1/pipelines/", payload, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["name"], "테스트 파이프라인")
        self.assertEqual(response.data["type"], "A")
        self.assertIn("id", response.data)

    def test_create_pipeline_b_type(self):
        """이메일수신형(B) 파이프라인 생성 — trigger_meta에 이메일 주소 저장."""
        payload = {
            "name": "이메일 수신 파이프라인",
            "type": "B",
            "trigger_meta": {"email": "inbox@officeax.com"},
            "is_active": True,
        }
        response = self.client.post("/api/v1/pipelines/", payload, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["trigger_meta"]["email"], "inbox@officeax.com")

    def test_create_pipeline_invalid_type(self):
        """지원하지 않는 type 값이면 400 반환."""
        payload = {"name": "잘못된 타입", "type": "Z"}
        response = self.client.post("/api/v1/pipelines/", payload, format="json")
        self.assertEqual(response.status_code, 400)

    def test_list_shows_only_own_pipelines(self):
        """다른 유저의 파이프라인은 목록에 포함되지 않는다."""
        other_user = _make_user(username="other_pipe")
        other_client = _authed_client(other_user)
        other_client.post(
            "/api/v1/pipelines/",
            {"name": "타인 파이프라인", "type": "A"},
            format="json",
        )

        # 내 계정으로 조회
        self.client.post(
            "/api/v1/pipelines/",
            {"name": "내 파이프라인", "type": "C"},
            format="json",
        )
        response = self.client.get("/api/v1/pipelines/")
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], "내 파이프라인")

    def test_unauthenticated_returns_401(self):
        """인증 없이 접근 시 401 반환."""
        response = APIClient().get("/api/v1/pipelines/")
        self.assertEqual(response.status_code, 401)


class PipelineDetailTest(TestCase):
    """GET / PATCH / DELETE /api/v1/pipelines/{id}/ 테스트."""

    def setUp(self):
        self.user = _make_user(username="pipe_detail")
        self.client = _authed_client(self.user)
        # 파이프라인 하나 생성
        res = self.client.post(
            "/api/v1/pipelines/",
            {"name": "상세 테스트 파이프라인", "type": "C", "trigger_meta": {"cron": "0 9 * * 1"}},
            format="json",
        )
        self.pipeline_id = res.data["id"]

    def test_retrieve_pipeline(self):
        """단건 조회 — trigger_meta 포함 응답 검증."""
        response = self.client.get(f"/api/v1/pipelines/{self.pipeline_id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["trigger_meta"]["cron"], "0 9 * * 1")

    def test_patch_pipeline_name(self):
        """PATCH로 이름 부분 수정."""
        response = self.client.patch(
            f"/api/v1/pipelines/{self.pipeline_id}/",
            {"name": "수정된 이름"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["name"], "수정된 이름")
        # type은 변경되지 않아야 함
        self.assertEqual(response.data["type"], "C")

    def test_patch_deactivate(self):
        """PATCH로 is_active False 변경."""
        response = self.client.patch(
            f"/api/v1/pipelines/{self.pipeline_id}/",
            {"is_active": False},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["is_active"])

    def test_delete_pipeline(self):
        """DELETE 후 404 반환 확인."""
        del_resp = self.client.delete(f"/api/v1/pipelines/{self.pipeline_id}/")
        self.assertEqual(del_resp.status_code, 204)
        get_resp = self.client.get(f"/api/v1/pipelines/{self.pipeline_id}/")
        self.assertEqual(get_resp.status_code, 404)

    def test_other_user_cannot_access(self):
        """다른 유저는 단건 조회/수정/삭제 불가 (404)."""
        other_client = _authed_client(_make_user(username="pipe_stranger"))
        self.assertEqual(other_client.get(f"/api/v1/pipelines/{self.pipeline_id}/").status_code, 404)
        self.assertEqual(
            other_client.patch(f"/api/v1/pipelines/{self.pipeline_id}/", {"name": "해킹"}, format="json").status_code,
            404,
        )
        self.assertEqual(other_client.delete(f"/api/v1/pipelines/{self.pipeline_id}/").status_code, 404)

    def test_owner_field_is_read_only(self):
        """owner 필드는 응답에 포함되되, 요청으로 변경 불가."""
        other = _make_user(username="pipe_owner_override")
        response = self.client.patch(
            f"/api/v1/pipelines/{self.pipeline_id}/",
            {"owner": other.pk},
            format="json",
        )
        # 수정 성공해도 owner는 바뀌지 않아야 함
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["owner"], self.user.pk)
