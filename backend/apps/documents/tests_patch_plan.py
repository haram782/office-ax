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
import shutil
import tempfile
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.documents.models import (
    DocumentChange,
    DocumentVersion,
    FileStructure,
    UploadLog,
)
from apps.documents.services.patch_plan import LLMParseError, _generate_patch_plan

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
            "document_text": "문서 본문 test",
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


class PatchPlanLLMDispatchTest(TestCase):
    """PatchPlan LLM 호출이 backend SDK가 아니라 ax-engine 태스크로 위임되는지 검증."""

    @patch("apps.documents.services.patch_plan.current_app.send_task")
    def test_generate_patch_plan_delegates_to_ax_engine_task(self, mock_send_task):
        """_generate_patch_plan은 tasks.generate_patch_plan을 ax 큐로 보내고 결과를 기다린다."""
        async_result = MagicMock()
        async_result.get.return_value = _MOCK_PATCH_PLAN
        mock_send_task.return_value = async_result

        plan = _generate_patch_plan(
            "날짜 형식을 고쳐줘",
            {"filename": "sample.xlsx", "source_type": "excel", "snippet_data": {}},
        )

        self.assertEqual(plan["plan_id"], "plan_test_001")
        mock_send_task.assert_called_once()
        self.assertEqual(mock_send_task.call_args.args[0], "tasks.generate_patch_plan")
        self.assertEqual(mock_send_task.call_args.kwargs["queue"], "ax")
        self.assertEqual(
            mock_send_task.call_args.kwargs["kwargs"]["prompt"],
            "날짜 형식을 고쳐줘",
        )
        async_result.get.assert_called_once()

    @patch("apps.documents.services.patch_plan.current_app.send_task")
    def test_generate_patch_plan_passes_document_text_to_ax_engine(self, mock_send_task):
        """UploadLog.result.document_text가 ax-engine file_context로 전달된다."""
        async_result = MagicMock()
        async_result.get.return_value = _MOCK_EMPTY_PLAN
        mock_send_task.return_value = async_result

        user = _make_user("patch_plan_context_user")
        upload = _make_done_upload(user, hash_val="patch_plan_context_hash")

        from apps.documents.services.patch_plan import PatchPlanService

        PatchPlanService.generate(upload.pk, "test를 수정해줘", user)

        file_context = mock_send_task.call_args.kwargs["kwargs"]["file_context"]
        self.assertEqual(file_context["document_text"], "문서 본문 test")

    @patch("apps.documents.services.patch_plan.current_app.send_task")
    def test_generate_patch_plan_passes_source_file_path_to_ax_engine(self, mock_send_task):
        """document_text가 없는 기존 분석 레코드도 ax-engine이 원본 파일을 다시 읽을 수 있어야 한다."""
        async_result = MagicMock()
        async_result.get.return_value = _MOCK_EMPTY_PLAN
        mock_send_task.return_value = async_result

        user = _make_user("patch_plan_file_path_user")
        upload = _make_done_upload(user, hash_val="patch_plan_file_path_hash")
        upload.result.pop("document_text", None)
        upload.file.name = "uploads/sample.hwp"
        upload.save(update_fields=["result", "file"])

        from apps.documents.services.patch_plan import PatchPlanService

        with patch.object(upload.file.storage, "path", return_value="/tmp/sample.hwp"):
            PatchPlanService.generate(upload.pk, "test를 수정해줘", user)

        file_context = mock_send_task.call_args.kwargs["kwargs"]["file_context"]
        self.assertEqual(file_context["document_text"], "")
        self.assertEqual(file_context["file_path"], "/tmp/sample.hwp")


_PDF_TEMP_MEDIA = tempfile.mkdtemp(prefix="office_ax_patch_plan_pdf_test_")


def teardown_module(_module):
    """모듈 종료 시 임시 디렉터리 삭제."""
    shutil.rmtree(_PDF_TEMP_MEDIA, ignore_errors=True)


def _build_pdf_bytes_cjk(text: str) -> bytes:
    """CJK 문자가 포함된 텍스트를 실제로 검색 가능하게 삽입한 단일 페이지 PDF."""
    import fitz
    import io
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 100), text, fontsize=12, fontname="korea-s", color=(0, 0, 0))
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


@override_settings(MEDIA_ROOT=_PDF_TEMP_MEDIA)
class PersistPatchPlanPdfPreviewAnchorTest(TestCase):
    """
    persist_patch_plan이 PDF text_match anchor의 미리보기 하이라이트
    (preview_anchor)를 계산해 DocumentChange에 저장하는지 검증한다.

    [버그 수정] 이 변환이 없으면 PDF 제안은 anchor.type이 항상 text_match라
    프론트엔드(PdfPageCanvas, pdf_bbox 전용)가 하이라이트를 그릴 좌표를
    받지 못해 아무것도 표시되지 않았다(실사용 재현).
    """

    def setUp(self):
        self.user = _make_user("pdf_preview_anchor_user")
        fs, _ = FileStructure.objects.get_or_create(
            hash="pdf_preview_anchor_hash",
            defaults={"source_type": FileStructure.SourceType.PDF, "column_schema": []},
        )
        self.upload = UploadLog.objects.create(
            user=self.user,
            file_structure=fs,
            original_filename="sample.pdf",
            status=UploadLog.Status.DONE,
            result={"source_type": "pdf", "summary": "분석 완료", "document_text": "본문"},
        )
        self.upload.file.save(
            "sample.pdf", ContentFile(_build_pdf_bytes_cjk("담당자 이메일 확인 요망")), save=True,
        )

    def tearDown(self):
        try:
            if self.upload.file:
                self.upload.file.delete(save=False)
        except Exception:
            pass

    def test_resolved_text_match_gets_preview_anchor_saved(self):
        from apps.documents.services.patch_plan import PatchPlanService

        plan = {
            "plan_id": "plan_pdf_preview_001",
            "summary": "이메일 확인 문구 강조",
            "operations": [{
                "operation_id": "op_001",
                "format": "pdf",
                "operation": "annotate",
                "title": "이메일 확인 강조",
                "original": "",
                "replacement": "",
                "reason": "테스트",
                "confidence": 0.9,
                "anchor": {"type": "text_match", "target_text": "이메일", "occurrence": 1},
                "patch": {},
                "risk": {"level": "low"},
            }],
        }

        result = PatchPlanService.persist_patch_plan(self.upload, "이메일 문구 강조해줘", self.user, plan)

        change = DocumentChange.objects.get(pk=result["changes"][0]["id"])
        self.assertEqual(change.preview_anchor.get("page"), 1)
        rect = change.preview_anchor.get("rect")
        self.assertIsNotNone(rect)
        self.assertIn("x0", rect)
        # API 응답 dict에도 그대로 포함돼야 프론트가 받을 수 있다
        self.assertEqual(result["changes"][0]["preview_anchor"], change.preview_anchor)

    def test_ambiguous_text_match_leaves_preview_anchor_empty(self):
        """모호한 경우(여러 후보) 잘못 추측해 표시하지 않고 빈 dict로 남긴다."""
        from apps.documents.services.patch_plan import PatchPlanService

        plan = {
            "plan_id": "plan_pdf_preview_002",
            "summary": "테스트",
            "operations": [{
                "operation_id": "op_001",
                "format": "pdf",
                "operation": "annotate",
                "title": "테스트",
                "original": "",
                "replacement": "",
                "reason": "테스트",
                "confidence": 0.9,
                # occurrence 없이 존재하지 않는 문구 — NOT_FOUND로 preview_anchor 없음
                "anchor": {"type": "text_match", "target_text": "존재하지 않는 문구"},
                "patch": {},
                "risk": {"level": "low"},
            }],
        }

        result = PatchPlanService.persist_patch_plan(self.upload, "테스트", self.user, plan)

        change = DocumentChange.objects.get(pk=result["changes"][0]["id"])
        self.assertEqual(change.preview_anchor, {})
