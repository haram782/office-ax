"""
버전 목록 API + on-demand 파일 반환 API 테스트.

커버 범위:
  GET /api/v1/uploads/{upload_id}/versions/
    - 소유자: 버전 목록 반환
    - 타인 소유 upload_id: 403
  GET /api/v1/uploads/{upload_id}/versions/{version_id}/file/
    - ready 상태: 파일 bytes 반환 (Content-Disposition 헤더 포함)
    - status != ready: 409
    - 타인 소유: 403
  _patch_* 함수가 bytes를 반환하는지
    - _patch_xlsx, _patch_docx, _patch_pptx 각각 bytes 확인
"""
import io
import tempfile

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

User = get_user_model()

TEMP_MEDIA = tempfile.mkdtemp()


def teardown_module(_module):
    import shutil
    shutil.rmtree(TEMP_MEDIA, ignore_errors=True)


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────

def _make_user(username):
    return User.objects.create_user(username=username, password="pw")


def _authed(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def _make_upload(user, source_type, filename, file_bytes, hash_val=None):
    _hash = hash_val or f"hash_{source_type}_{filename}"
    fs, _ = FileStructure.objects.get_or_create(
        hash=_hash,
        defaults={"source_type": source_type, "column_schema": []},
    )
    upload = UploadLog.objects.create(
        user=user,
        file_structure=fs,
        original_filename=filename,
        status=UploadLog.Status.DONE,
    )
    upload.file.save(filename, ContentFile(file_bytes), save=True)
    return upload


def _make_version(upload, user, status=DocumentVersion.Status.READY, version_number=2):
    return DocumentVersion.objects.create(
        upload_log=upload,
        version_number=version_number,
        status=status,
        label="수정본",
        applied_change_ids=["op_001"],
        created_by=user,
    )


def _make_change(version, operation_id, operation, anchor, original="", replacement="",
                 status=DocumentChange.Status.APPLIED):
    return DocumentChange.objects.create(
        version=version,
        operation_id=operation_id,
        operation=operation,
        title="테스트",
        original=original,
        replacement=replacement,
        anchor=anchor,
        confidence=0.9,
        status=status,
    )


def _xlsx_bytes_with_value(sheet_name, cell, value):
    """지정 셀에 값이 있는 최소 XLSX 바이트를 생성한다."""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name
    ws[cell] = value
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _docx_bytes_with_text(text):
    from docx import Document
    doc = Document()
    doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _pptx_bytes_with_text(text):
    from pptx import Presentation
    from pptx.util import Inches
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    txBox = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1))
    txBox.text_frame.text = text
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


# ── 버전 목록 API 테스트 ─────────────────────────────────────────────────────


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class DocumentVersionListTest(TestCase):
    """GET /api/v1/uploads/{upload_id}/versions/"""

    def setUp(self):
        self.user = _make_user("ver_list_user")
        self.client = _authed(self.user)
        self.upload = _make_upload(self.user, "excel", "test.xlsx", b"dummy", "ver_list_hash")
        # 버전 두 개 생성
        DocumentVersion.objects.create(
            upload_log=self.upload, version_number=1,
            status=DocumentVersion.Status.ORIGINAL, label="원본", created_by=self.user,
        )
        DocumentVersion.objects.create(
            upload_log=self.upload, version_number=2,
            status=DocumentVersion.Status.READY, label="수정본",
            applied_change_ids=["op_001"], created_by=self.user,
        )

    def test_list_returns_versions(self):
        """소유자가 조회하면 버전 목록이 반환된다."""
        resp = self.client.get(f"/api/v1/uploads/{self.upload.pk}/versions/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 2)

    def test_list_contains_expected_fields(self):
        """응답에 id, version_number, status, label, applied_change_ids, created_at이 포함된다."""
        resp = self.client.get(f"/api/v1/uploads/{self.upload.pk}/versions/")
        self.assertEqual(resp.status_code, 200)
        item = resp.data[0]
        for field in ("id", "version_number", "status", "label", "applied_change_ids", "created_at"):
            self.assertIn(field, item, f"응답에 {field} 필드가 있어야 한다")

    def test_other_user_gets_403(self):
        """타인 소유 upload_id → 403."""
        other = _make_user("ver_list_other")
        resp = _authed(other).get(f"/api/v1/uploads/{self.upload.pk}/versions/")
        self.assertEqual(resp.status_code, 403)


# ── 버전 파일 on-demand API 테스트 ─────────────────────────────────────────--


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class DocumentVersionFileTest(TestCase):
    """GET /api/v1/uploads/{upload_id}/versions/{version_id}/file/"""

    def setUp(self):
        self.user = _make_user("ver_file_user")
        self.client = _authed(self.user)

    def _setup_xlsx(self):
        file_bytes = _xlsx_bytes_with_value("Sheet1", "A1", "원본값")
        upload = _make_upload(self.user, "excel", "test.xlsx", file_bytes, "ver_file_xlsx")
        version = _make_version(upload, self.user, status=DocumentVersion.Status.READY)
        _make_change(
            version, "op_001", "replace_cell",
            anchor={"type": "cell", "sheet": "Sheet1", "cell": "A1"},
            original="원본값", replacement="수정값",
        )
        return upload, version

    def test_ready_version_returns_file(self):
        """ready 상태 버전 → 파일 bytes 응답."""
        upload, version = self._setup_xlsx()
        resp = self.client.get(
            f"/api/v1/uploads/{upload.pk}/versions/{version.pk}/file/"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertGreater(len(resp.content), 0, "파일 내용이 비어 있으면 안 된다")

    def test_response_has_content_disposition(self):
        """Content-Disposition 헤더가 attachment 형식으로 설정된다."""
        upload, version = self._setup_xlsx()
        resp = self.client.get(
            f"/api/v1/uploads/{upload.pk}/versions/{version.pk}/file/"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("attachment", resp.get("Content-Disposition", ""))

    def test_non_ready_version_returns_409(self):
        """status != ready인 버전 → 409 Conflict."""
        file_bytes = _xlsx_bytes_with_value("Sheet1", "A1", "값")
        upload = _make_upload(self.user, "excel", "draft.xlsx", file_bytes, "ver_file_draft")
        draft_version = _make_version(
            upload, self.user,
            status=DocumentVersion.Status.DRAFT,
        )
        resp = self.client.get(
            f"/api/v1/uploads/{upload.pk}/versions/{draft_version.pk}/file/"
        )
        self.assertEqual(resp.status_code, 409)

    def test_other_user_gets_403(self):
        """타인 소유 upload_id → 403."""
        upload, version = self._setup_xlsx()
        other = _make_user("ver_file_other")
        resp = _authed(other).get(
            f"/api/v1/uploads/{upload.pk}/versions/{version.pk}/file/"
        )
        self.assertEqual(resp.status_code, 403)


# ── _patch_* 순수 함수 bytes 반환 테스트 ─────────────────────────────────────


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class PatchFunctionReturnsBytesTest(TestCase):
    """각 _patch_* 함수가 bytes를 반환하는지 검증한다."""

    def setUp(self):
        self.user = _make_user("patch_bytes_user")

    def _make_full_upload(self, source_type, filename, file_bytes, hash_val):
        return _make_upload(self.user, source_type, filename, file_bytes, hash_val)

    def test_patch_xlsx_returns_bytes(self):
        """_patch_xlsx가 apply 성공 시 bytes를 반환한다."""
        from apps.documents.tasks import _patch_xlsx

        file_bytes = _xlsx_bytes_with_value("Sheet1", "B2", "old")
        upload = self._make_full_upload("excel", "t.xlsx", file_bytes, "bytes_xlsx")
        version = _make_version(upload, self.user, status=DocumentVersion.Status.DRAFT)
        _make_change(
            version, "op_x01", "replace_cell",
            anchor={"type": "cell", "sheet": "Sheet1", "cell": "B2"},
            original="old", replacement="new",
        )

        result = _patch_xlsx(version, upload)
        self.assertIsInstance(result, (bytes, bytearray), "_patch_xlsx는 bytes를 반환해야 한다")

    def test_patch_docx_returns_bytes(self):
        """_patch_docx가 apply 성공 시 bytes를 반환한다."""
        from apps.documents.tasks import _patch_docx

        file_bytes = _docx_bytes_with_text("원본 텍스트")
        upload = self._make_full_upload("docx", "t.docx", file_bytes, "bytes_docx")
        version = _make_version(upload, self.user, status=DocumentVersion.Status.DRAFT)
        _make_change(
            version, "op_d01", "replace_text",
            anchor={"type": "text_match", "text_match": "원본 텍스트"},
            original="원본 텍스트", replacement="수정 텍스트",
        )

        result = _patch_docx(version, upload)
        self.assertIsInstance(result, (bytes, bytearray), "_patch_docx는 bytes를 반환해야 한다")

    def test_patch_pptx_returns_bytes(self):
        """_patch_pptx가 apply 성공 시 bytes를 반환한다."""
        from apps.documents.tasks import _patch_pptx

        file_bytes = _pptx_bytes_with_text("슬라이드 텍스트")
        upload = self._make_full_upload("pptx", "t.pptx", file_bytes, "bytes_pptx")
        version = _make_version(upload, self.user, status=DocumentVersion.Status.DRAFT)
        _make_change(
            version, "op_p01", "replace_text",
            anchor={"type": "slide_shape", "slide_index": 0, "shape_index": 0,
                    "text_match": "슬라이드 텍스트"},
            original="슬라이드 텍스트", replacement="수정된 텍스트",
        )

        result = _patch_pptx(version, upload)
        self.assertIsInstance(result, (bytes, bytearray), "_patch_pptx는 bytes를 반환해야 한다")
