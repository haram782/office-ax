"""
DocumentChange apply/reject API 테스트.

커버 범위:
  GET  /api/v1/uploads/{upload_id}/changes/
  PATCH /api/v1/changes/{id}/
  POST  /api/v1/uploads/{upload_id}/versions/
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.documents.models import (
    DocumentChange,
    DocumentVersion,
    FileStructure,
    UploadLog,
)

User = get_user_model()


# ── 픽스처 헬퍼 ────────────────────────────────────────────────────────────────

def _make_user(username):
    return User.objects.create_user(username=username, password="pw")


def _authed(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def _make_upload(user, hash_val="patch_api_hash"):
    fs, _ = FileStructure.objects.get_or_create(
        hash=hash_val,
        defaults={"source_type": FileStructure.SourceType.PDF, "column_schema": []},
    )
    return UploadLog.objects.create(
        user=user,
        file_structure=fs,
        original_filename="sample.pdf",
    )


def _make_version(upload, user):
    return DocumentVersion.objects.create(
        upload_log=upload,
        created_by=user,
    )


def _make_change(version, operation_id="op_001", status="pending"):
    return DocumentChange.objects.create(
        version=version,
        operation_id=operation_id,
        format="pdf",
        operation="annotate",
        original="",
        replacement="확인 필요",
        reason="누락 항목",
        confidence=0.9,
        status=status,
    )


# ── GET /api/v1/uploads/{upload_id}/changes/ ───────────────────────────────────

class DocumentChangeListTest(TestCase):
    """DocumentChange 목록 조회 테스트."""

    def setUp(self):
        self.user = _make_user("list_user")
        self.client = _authed(self.user)
        self.upload = _make_upload(self.user)
        self.version = _make_version(self.upload, self.user)
        self.change = _make_change(self.version, "op_list_001")

    def test_returns_own_upload_changes(self):
        """본인 소유 upload의 change 목록을 반환한다."""
        resp = self.client.get(f"/api/v1/uploads/{self.upload.pk}/changes/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]["operation_id"], "op_list_001")

    def test_other_user_upload_returns_404(self):
        """타인 소유 upload 조회 시 404를 반환한다."""
        other = _make_user("list_other")
        other_upload = _make_upload(other, hash_val="other_hash_list")
        resp = self.client.get(f"/api/v1/uploads/{other_upload.pk}/changes/")
        self.assertEqual(resp.status_code, 404)

    def test_response_includes_required_fields(self):
        """응답에 필수 필드가 모두 포함되어야 한다."""
        resp = self.client.get(f"/api/v1/uploads/{self.upload.pk}/changes/")
        self.assertEqual(resp.status_code, 200)
        record = resp.data[0]
        for field in [
            "id", "operation_id", "plan_id", "format", "operation", "title",
            "original", "replacement", "reason", "confidence",
            "anchor", "patch", "risk_level", "status", "created_at", "updated_at",
        ]:
            self.assertIn(field, record, f"응답에 {field} 필드가 없습니다.")

    def test_version_id_filter(self):
        """?version_id= 쿼리로 특정 버전의 change만 반환한다."""
        version2 = _make_version(self.upload, self.user)
        _make_change(version2, "op_v2_001")

        resp = self.client.get(
            f"/api/v1/uploads/{self.upload.pk}/changes/",
            {"version_id": self.version.pk},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]["operation_id"], "op_list_001")

    def test_unauthenticated_returns_401(self):
        """인증 없이 접근 시 401을 반환한다."""
        resp = APIClient().get(f"/api/v1/uploads/{self.upload.pk}/changes/")
        self.assertEqual(resp.status_code, 401)


# ── PATCH /api/v1/changes/{id}/ ───────────────────────────────────────────────

class DocumentChangePatchTest(TestCase):
    """DocumentChange status 전이 테스트."""

    def setUp(self):
        self.user = _make_user("patch_user")
        self.client = _authed(self.user)
        self.upload = _make_upload(self.user, hash_val="patch_hash")
        self.version = _make_version(self.upload, self.user)

    def _change(self, op_id="op_patch_001", status="pending"):
        return _make_change(self.version, op_id, status)

    def test_pending_to_applied(self):
        """pending → applied 전이가 성공해야 한다."""
        ch = self._change()
        resp = self.client.patch(
            f"/api/v1/changes/{ch.pk}/", {"status": "applied"}, format="json"
        )
        self.assertEqual(resp.status_code, 200)
        ch.refresh_from_db()
        self.assertEqual(ch.status, "applied")

    def test_pending_to_rejected(self):
        """pending → rejected 전이가 성공해야 한다."""
        ch = self._change(op_id="op_patch_002")
        resp = self.client.patch(
            f"/api/v1/changes/{ch.pk}/", {"status": "rejected"}, format="json"
        )
        self.assertEqual(resp.status_code, 200)
        ch.refresh_from_db()
        self.assertEqual(ch.status, "rejected")

    def test_applied_to_pending(self):
        """applied → pending 전이(적용 취소)가 성공해야 한다."""
        ch = self._change(op_id="op_patch_003", status="applied")
        resp = self.client.patch(
            f"/api/v1/changes/{ch.pk}/", {"status": "pending"}, format="json"
        )
        self.assertEqual(resp.status_code, 200)
        ch.refresh_from_db()
        self.assertEqual(ch.status, "pending")

    def test_rejected_to_pending(self):
        """rejected → pending 전이(거절 취소)가 성공해야 한다."""
        ch = self._change(op_id="op_patch_004", status="rejected")
        resp = self.client.patch(
            f"/api/v1/changes/{ch.pk}/", {"status": "pending"}, format="json"
        )
        self.assertEqual(resp.status_code, 200)
        ch.refresh_from_db()
        self.assertEqual(ch.status, "pending")

    def test_applied_to_rejected_returns_400(self):
        """applied → rejected 직접 전이는 허용되지 않으므로 400을 반환한다."""
        ch = self._change(op_id="op_patch_005", status="applied")
        resp = self.client.patch(
            f"/api/v1/changes/{ch.pk}/", {"status": "rejected"}, format="json"
        )
        self.assertEqual(resp.status_code, 400)
        # DB 상태가 변경되지 않아야 한다.
        ch.refresh_from_db()
        self.assertEqual(ch.status, "applied")

    def test_other_user_change_returns_403(self):
        """타인 소유 change 수정 시 403을 반환한다."""
        other = _make_user("patch_other")
        other_upload = _make_upload(other, hash_val="patch_other_hash")
        other_version = _make_version(other_upload, other)
        other_change = _make_change(other_version, "op_other_001")

        resp = self.client.patch(
            f"/api/v1/changes/{other_change.pk}/",
            {"status": "applied"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_response_includes_full_change_fields(self):
        """성공 응답에 수정된 DocumentChange 전체 필드가 포함되어야 한다."""
        ch = self._change(op_id="op_patch_006")
        resp = self.client.patch(
            f"/api/v1/changes/{ch.pk}/", {"status": "applied"}, format="json"
        )
        self.assertEqual(resp.status_code, 200)
        for field in ["id", "operation_id", "status", "updated_at"]:
            self.assertIn(field, resp.data)


# ── POST /api/v1/uploads/{upload_id}/versions/ ───────────────────────────────

class DocumentVersionCreateTest(TestCase):
    """DocumentVersion 생성 API 테스트."""

    def setUp(self):
        self.user = _make_user("version_create_user")
        self.client = _authed(self.user)
        self.upload = _make_upload(self.user, hash_val="version_create_hash")

    def test_creates_draft_version(self):
        """POST 시 draft 상태의 DocumentVersion이 생성된다."""
        resp = self.client.post(
            f"/api/v1/uploads/{self.upload.pk}/versions/",
            {"label": "날짜 형식 통일", "summary": "날짜 오류 수정", "patch_plan": []},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["status"], "draft")

    def test_version_number_is_auto_assigned(self):
        """version_number가 자동 채번된다."""
        resp = self.client.post(
            f"/api/v1/uploads/{self.upload.pk}/versions/",
            {"label": "v1", "summary": "", "patch_plan": []},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["version_number"], 1)

    def test_second_version_gets_number_two(self):
        """두 번째 버전의 version_number는 2이다."""
        self.client.post(
            f"/api/v1/uploads/{self.upload.pk}/versions/",
            {"label": "v1", "summary": "", "patch_plan": []},
            format="json",
        )
        resp = self.client.post(
            f"/api/v1/uploads/{self.upload.pk}/versions/",
            {"label": "v2", "summary": "", "patch_plan": []},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["version_number"], 2)

    def test_other_user_upload_returns_403(self):
        """타인 소유 upload_id로 버전 생성 시 403을 반환한다."""
        other = _make_user("version_other")
        other_upload = _make_upload(other, hash_val="version_other_hash")

        resp = self.client.post(
            f"/api/v1/uploads/{other_upload.pk}/versions/",
            {"label": "test", "summary": "", "patch_plan": []},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_response_includes_required_fields(self):
        """응답에 id, version_number, status, label, created_at이 포함되어야 한다."""
        resp = self.client.post(
            f"/api/v1/uploads/{self.upload.pk}/versions/",
            {"label": "테스트 버전", "summary": "요약", "patch_plan": []},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        for field in ["id", "version_number", "status", "label", "created_at"]:
            self.assertIn(field, resp.data, f"응답에 {field} 필드가 없습니다.")
