"""
LLM → patch plan 생성 → DocumentChange 저장 API 테스트.

커버 범위:
  POST /api/v1/uploads/{upload_id}/generate-patch-plan/

테스트 케이스:
  1. 유효한 prompt + upload_id → DocumentVersion(draft) 생성됨
  2. 유효한 prompt + upload_id → DocumentChange 행들이 생성됨
  3. 응답에 id(changeDbId)가 포함됨
  4. 타인 소유 upload_id → 403
  5. upload_log.status != DONE → 400
  6. LLM JSON 파싱 실패 mock → 400
  7. operations 빈 배열 mock → 200 + changes=[]
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.documents.models import (
    DocumentChange,
    DocumentVersion,
    FileStructure,
    UploadLog,
)
from apps.documents.services.patch_plan import LLMParseError

User = get_user_model()

_URL = "/api/v1/uploads/{upload_id}/generate-patch-plan/"

# LLM mock이 반환할 PatchPlan 샘플
_MOCK_PATCH_PLAN = {
    "schema": "office_ax.patch_plan.v0",
    "plan_id": "plan_test_001",
    "summary": "날짜 형식 통일 제안을 생성했습니다.",
    "operations": [
        {
            "operation_id": "op_001",
            "format": "excel",
            "operation": "replace_cell",
            "title": "날짜 형식 통일",
            "original": "20260101",
            "replacement": "2026-01-01",
            "reason": "날짜 형식이 YYYY-MM-DD와 다릅니다.",
            "confidence": 0.92,
            "anchor": {"type": "cell", "sheet": "Sheet1", "cell": "A2"},
            "patch": {"method": "openpyxl_set_value", "value": "2026-01-01"},
            "risk": {"level": "low"},
        },
        {
            "operation_id": "op_002",
            "format": "excel",
            "operation": "replace_cell",
            "title": "날짜 형식 통일 2",
            "original": "20260201",
            "replacement": "2026-02-01",
            "reason": "날짜 형식이 YYYY-MM-DD와 다릅니다.",
            "confidence": 0.90,
            "anchor": {"type": "cell", "sheet": "Sheet1", "cell": "B2"},
            "patch": {"method": "openpyxl_set_value", "value": "2026-02-01"},
            "risk": {"level": "low"},
        },
    ],
}

_MOCK_EMPTY_PLAN = {
    "schema": "office_ax.patch_plan.v0",
    "plan_id": "plan_empty_001",
    "summary": "수정할 항목이 없습니다.",
    "operations": [],
}


# ── 픽스처 헬퍼 ───────────────────────────────────────────────────────────────


def _make_user(username):
    return User.objects.create_user(username=username, password="pw")


def _authed(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def _make_done_upload(user, hash_val="patch_plan_hash"):
    """status=DONE이고 result가 채워진 UploadLog 생성."""
    fs, _ = FileStructure.objects.get_or_create(
        hash=hash_val,
        defaults={"source_type": FileStructure.SourceType.EXCEL, "column_schema": []},
    )
    return UploadLog.objects.create(
        user=user,
        file_structure=fs,
        original_filename="sample.xlsx",
        status=UploadLog.Status.DONE,
        result={
            "source_type": "excel",
            "summary": "분석 완료",
            "errors": ["날짜 형식 오류"],
            "snippet_data": {
                "corrections": [{"cell": "A2", "issue": "날짜 형식 불일치"}]
            },
        },
    )


# ── 테스트 클래스 ─────────────────────────────────────────────────────────────


class GeneratePatchPlanTest(TestCase):
    """POST /api/v1/uploads/{upload_id}/generate-patch-plan/ 테스트."""

    def setUp(self):
        self.user = _make_user("patch_plan_user")
        self.client = _authed(self.user)
        self.upload = _make_done_upload(self.user)

    @patch("apps.documents.services.patch_plan._generate_patch_plan", return_value=_MOCK_PATCH_PLAN)
    def test_creates_draft_document_version(self, _mock):
        """유효한 prompt + upload_id → DocumentVersion(draft)이 생성된다."""
        resp = self.client.post(
            _URL.format(upload_id=self.upload.pk),
            {"prompt": "날짜 형식을 YYYY-MM-DD로 통일해줘"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(
            DocumentVersion.objects.filter(
                upload_log=self.upload,
                status=DocumentVersion.Status.DRAFT,
            ).exists(),
            "draft 상태의 DocumentVersion이 생성되어야 한다",
        )

    @patch("apps.documents.services.patch_plan._generate_patch_plan", return_value=_MOCK_PATCH_PLAN)
    def test_creates_document_changes(self, _mock):
        """유효한 prompt + upload_id → DocumentChange 행들이 생성된다."""
        resp = self.client.post(
            _URL.format(upload_id=self.upload.pk),
            {"prompt": "날짜 형식을 YYYY-MM-DD로 통일해줘"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        version_id = resp.data["version_id"]
        change_count = DocumentChange.objects.filter(version_id=version_id).count()
        self.assertEqual(
            change_count,
            2,
            "operations 2개에 해당하는 DocumentChange 행이 생성되어야 한다",
        )

    @patch("apps.documents.services.patch_plan._generate_patch_plan", return_value=_MOCK_PATCH_PLAN)
    def test_response_contains_change_db_id(self, _mock):
        """응답 changes 항목에 id(changeDbId)가 포함된다."""
        resp = self.client.post(
            _URL.format(upload_id=self.upload.pk),
            {"prompt": "날짜 형식을 YYYY-MM-DD로 통일해줘"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        changes = resp.data.get("changes", [])
        self.assertEqual(len(changes), 2)
        for ch in changes:
            self.assertIn("id", ch, "각 change 항목에 id(changeDbId)가 있어야 한다")
            self.assertIsNotNone(ch["id"])

    def test_other_user_upload_returns_403(self):
        """타인 소유 upload_id → 403을 반환한다."""
        other = _make_user("patch_plan_other")
        other_upload = _make_done_upload(other, hash_val="patch_plan_other_hash")

        resp = self.client.post(
            _URL.format(upload_id=other_upload.pk),
            {"prompt": "수정해줘"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_upload_not_done_returns_400(self):
        """upload_log.status != DONE → 400을 반환한다."""
        fs, _ = FileStructure.objects.get_or_create(
            hash="patch_plan_pending_hash",
            defaults={"source_type": FileStructure.SourceType.EXCEL, "column_schema": []},
        )
        pending_upload = UploadLog.objects.create(
            user=self.user,
            file_structure=fs,
            original_filename="pending.xlsx",
            status=UploadLog.Status.PROCESSING,
        )
        resp = self.client.post(
            _URL.format(upload_id=pending_upload.pk),
            {"prompt": "수정해줘"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    @patch(
        "apps.documents.services.patch_plan._generate_patch_plan",
        side_effect=LLMParseError("JSON 파싱 실패"),
    )
    def test_llm_parse_error_returns_400(self, _mock):
        """LLM JSON 파싱 실패 시 400을 반환한다."""
        resp = self.client.post(
            _URL.format(upload_id=self.upload.pk),
            {"prompt": "수정해줘"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("detail", resp.data)

    @patch("apps.documents.services.patch_plan._generate_patch_plan", return_value=_MOCK_EMPTY_PLAN)
    def test_empty_operations_returns_200_with_empty_changes(self, _mock):
        """operations가 빈 배열이면 200 + changes=[]를 반환한다."""
        resp = self.client.post(
            _URL.format(upload_id=self.upload.pk),
            {"prompt": "수정해줘"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data.get("changes"), [])
        self.assertIsNone(resp.data.get("version_id"))
