"""
버전 목록 API + artifact 저장 기반 파일 반환 API 테스트.

커버 범위:
  GET /api/v1/uploads/{upload_id}/versions/
    - 소유자: 버전 목록 반환
    - 타인 소유 upload_id: 403
  GET /api/v1/uploads/{upload_id}/versions/{version_id}/file/
    - ready 상태 + artifact_file 저장됨: 저장된 파일 bytes 그대로 반환
    - status != ready: 409
    - ready 상태인데 artifact_file이 비어있음(방어적 경계 케이스): 404
    - 타인 소유: 403
    - GET 반복 호출 시 DB write가 발생하지 않음(멱등성 회귀 테스트)
    - GET 호출 시 patcher 함수(_patch_pdf 등)가 호출되지 않음
  patch_document_version Celery task
    - 패치 성공 시 version.artifact_file에 실제 파일이 저장되는지
  _patch_* 함수가 bytes를 반환하는지
    - _patch_xlsx, _patch_docx, _patch_pptx 각각 bytes 확인
"""
import io
import tempfile
from unittest.mock import patch as mock_patch

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


def _make_version(upload, user, status=DocumentVersion.Status.READY, version_number=2,
                   artifact_bytes=None, artifact_ext="xlsx"):
    version = DocumentVersion.objects.create(
        upload_log=upload,
        version_number=version_number,
        status=status,
        label="수정본",
        applied_change_ids=["op_001"],
        created_by=user,
    )
    if artifact_bytes is not None:
        # 이미 patch가 완료되어 artifact_file이 저장된 상태를 시뮬레이션한다
        version.artifact_file.save(
            f"v{version.pk}.{artifact_ext}", ContentFile(artifact_bytes), save=False
        )
        version.artifact_format = artifact_ext
        version.save(update_fields=["artifact_file", "artifact_format"])
    return version


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
        # artifact_file에 patch 완료된 결과가 이미 저장된 상태로 생성
        artifact_bytes = _xlsx_bytes_with_value("Sheet1", "A1", "수정값")
        version = _make_version(
            upload, self.user, status=DocumentVersion.Status.READY,
            artifact_bytes=artifact_bytes, artifact_ext="xlsx",
        )
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

    def test_returned_content_matches_stored_artifact(self):
        """응답 내용이 저장된 artifact_file의 bytes와 정확히 일치한다(재생성이 아닌 저장본 반환 확인)."""
        upload, version = self._setup_xlsx()
        version.refresh_from_db()
        with version.artifact_file.open("rb") as f:
            stored_bytes = f.read()

        resp = self.client.get(
            f"/api/v1/uploads/{upload.pk}/versions/{version.pk}/file/"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, stored_bytes)

    def test_ready_without_artifact_file_returns_404(self):
        """status=ready인데 artifact_file이 비어있는 방어적 경계 케이스 → 404."""
        file_bytes = _xlsx_bytes_with_value("Sheet1", "A1", "값")
        upload = _make_upload(self.user, "excel", "no_artifact.xlsx", file_bytes, "ver_file_no_artifact")
        # artifact_bytes=None → artifact_file이 비어있는 ready 버전
        version = _make_version(upload, self.user, status=DocumentVersion.Status.READY)

        resp = self.client.get(
            f"/api/v1/uploads/{upload.pk}/versions/{version.pk}/file/"
        )
        self.assertEqual(resp.status_code, 404)

    def test_generating_status_returns_409(self):
        """status=generating(아직 생성 중)인 버전에 대한 GET → 409."""
        file_bytes = _xlsx_bytes_with_value("Sheet1", "A1", "값")
        upload = _make_upload(self.user, "excel", "generating.xlsx", file_bytes, "ver_file_generating")
        version = _make_version(upload, self.user, status=DocumentVersion.Status.GENERATING)

        resp = self.client.get(
            f"/api/v1/uploads/{upload.pk}/versions/{version.pk}/file/"
        )
        self.assertEqual(resp.status_code, 409)


class DocumentVersionFileIdempotencyTest(TestCase):
    """GET 반복 호출 시 DB write가 발생하지 않는지 검증하는 회귀 테스트(멱등성 핵심 버그)."""

    def setUp(self):
        self.user = _make_user("ver_file_idem_user")
        self.client = _authed(self.user)

        file_bytes = _xlsx_bytes_with_value("Sheet1", "A1", "원본값")
        self.upload = _make_upload(self.user, "excel", "idem.xlsx", file_bytes, "ver_file_idem")
        artifact_bytes = _xlsx_bytes_with_value("Sheet1", "A1", "수정값")
        self.version = _make_version(
            self.upload, self.user, status=DocumentVersion.Status.READY,
            artifact_bytes=artifact_bytes, artifact_ext="xlsx",
        )
        self.change = _make_change(
            self.version, "op_idem", "replace_cell",
            anchor={"type": "cell", "sheet": "Sheet1", "cell": "A1"},
            original="원본값", replacement="수정값",
        )

    def test_repeated_get_does_not_mutate_updated_at(self):
        self.version.refresh_from_db()
        self.change.refresh_from_db()
        version_updated_before = self.version.updated_at
        change_updated_before = self.change.updated_at

        url = f"/api/v1/uploads/{self.upload.pk}/versions/{self.version.pk}/file/"
        self.client.get(url)
        self.client.get(url)

        self.version.refresh_from_db()
        self.change.refresh_from_db()

        self.assertEqual(
            self.version.updated_at, version_updated_before,
            "GET 반복 호출이 DocumentVersion.updated_at을 변경하면 안 된다",
        )
        self.assertEqual(
            self.change.updated_at, change_updated_before,
            "GET 반복 호출이 DocumentChange.updated_at을 변경하면 안 된다",
        )


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class DocumentVersionFileDoesNotCallPatcherTest(TestCase):
    """GET 호출이 더 이상 patcher 함수를 호출하지 않는지 mock으로 검증한다(PDF 포맷 기준)."""

    def setUp(self):
        self.user = _make_user("ver_file_nopatch_user")
        self.client = _authed(self.user)

        # PDF 최소 바이트 — fitz 의존 없이 단순 더미로 충분(patcher가 호출되지 않아야 하므로)
        upload = _make_upload(self.user, "pdf", "doc.pdf", b"%PDF-1.4 dummy", "ver_file_nopatch")
        artifact_bytes = b"%PDF-1.4 patched dummy"
        self.version = _make_version(
            upload, self.user, status=DocumentVersion.Status.READY,
            artifact_bytes=artifact_bytes, artifact_ext="pdf",
        )
        self.upload = upload

    def test_get_does_not_invoke_patch_pdf(self):
        with mock_patch("apps.documents.tasks._patch_pdf") as mocked_patcher:
            resp = self.client.get(
                f"/api/v1/uploads/{self.upload.pk}/versions/{self.version.pk}/file/"
            )
            self.assertEqual(resp.status_code, 200)
            mocked_patcher.assert_not_called()


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class PatchDocumentVersionSavesArtifactTest(TestCase):
    """patch_document_version Celery task가 실제로 artifact_file을 저장하는지 검증한다."""

    def setUp(self):
        self.user = _make_user("patch_save_user")

    def test_patch_success_saves_artifact_file(self):
        from apps.documents.tasks import patch_document_version

        file_bytes = _xlsx_bytes_with_value("Sheet1", "C3", "old")
        upload = _make_upload(self.user, "excel", "save.xlsx", file_bytes, "patch_save_hash")
        version = _make_version(upload, self.user, status=DocumentVersion.Status.DRAFT)
        _make_change(
            version, "op_save01", "replace_cell",
            anchor={"type": "cell", "sheet": "Sheet1", "cell": "C3"},
            original="old", replacement="new",
        )

        patch_document_version(version.pk)

        version.refresh_from_db()
        self.assertTrue(bool(version.artifact_file), "patch 성공 시 artifact_file이 저장되어야 한다")
        with version.artifact_file.open("rb") as f:
            content = f.read()
        self.assertGreater(len(content), 0, "저장된 artifact_file 내용이 비어 있으면 안 된다")
        self.assertEqual(version.artifact_format, "xlsx")


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
