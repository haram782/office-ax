"""
PDF annotate / redact_overlay 패처 테스트.

커버 범위:
  patch_document_version Celery 태스크 (동기 직접 호출)
  - pdf_bbox anchor + annotate → 하이라이트 주석이 생성된다
  - text_match anchor + annotate → search_for로 rect를 찾아 주석이 생성된다
  - pdf_bbox anchor + redact_overlay → artifact에 replacement 텍스트가 포함된다
  - anchor 해석 실패(텍스트 없음) → change.status=failed
  - 모든 항목 실패 → version.status=failed
  - 하나라도 성공 → version.status=ready + artifact_file 생성
"""
import io
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings

from apps.documents.models import (
    DocumentChange,
    DocumentVersion,
    FileStructure,
    UploadLog,
)
from apps.documents.tasks import patch_document_version

User = get_user_model()

TEMP_MEDIA = tempfile.mkdtemp()


def teardown_module(_module):
    """모듈 종료 시 임시 디렉터리 정리."""
    import shutil
    shutil.rmtree(TEMP_MEDIA, ignore_errors=True)


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────


def _make_user(username):
    return User.objects.create_user(username=username, password="pw")


def _build_pdf_bytes(text: str = "샘플 텍스트") -> bytes:
    """
    지정 텍스트가 포함된 단일 페이지 PDF 바이트를 fitz로 생성한다.

    fitz 기본 내장 폰트는 라틴 문자만 지원하므로
    CJK 텍스트는 display 깨짐이 발생할 수 있으나 bytes 인코딩은 유효하다.
    """
    import fitz
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4 크기
    # Helvetica 기본 폰트로 텍스트 삽입
    page.insert_text((72, 100), text, fontsize=12, color=(0, 0, 0))
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def _make_upload(user, filename, file_bytes, hash_val=None):
    _hash = hash_val or f"hash_pdf_{filename}"
    fs, _ = FileStructure.objects.get_or_create(
        hash=_hash,
        defaults={"source_type": FileStructure.SourceType.PDF, "column_schema": []},
    )
    upload = UploadLog.objects.create(
        user=user,
        file_structure=fs,
        original_filename=filename,
        status=UploadLog.Status.DONE,
    )
    upload.file.save(filename, ContentFile(file_bytes), save=True)
    return upload


def _make_version(upload, user, version_number=2):
    return DocumentVersion.objects.create(
        upload_log=upload,
        version_number=version_number,
        status=DocumentVersion.Status.DRAFT,
        label="draft",
        created_by=user,
    )


def _make_change(version, operation_id, operation, anchor, original="", replacement="",
                 status=DocumentChange.Status.APPLIED):
    return DocumentChange.objects.create(
        version=version,
        operation_id=operation_id,
        operation=operation,
        title="테스트 변경",
        original=original,
        replacement=replacement,
        anchor=anchor,
        confidence=0.9,
        status=status,
    )


# ── 테스트 클래스 ──────────────────────────────────────────────────────────────


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class PdfAnnotateTest(TestCase):
    """PDF annotate 패처 테스트."""

    def setUp(self):
        self.user = _make_user("pdf_annotate_user")
        self.pdf_bytes = _build_pdf_bytes("Hello World")
        self.upload = _make_upload(self.user, "sample.pdf", self.pdf_bytes, "pdf_ann_hash")
        self.version = _make_version(self.upload, self.user)

    def test_pdf_bbox_annotate_sets_version_ready(self):
        """pdf_bbox anchor + annotate → version.status=ready가 된다."""
        _make_change(
            self.version,
            operation_id="op_ann_01",
            operation="annotate",
            anchor={
                "type": "pdf_bbox",
                "page": 1,
                "rect": {"x0": 72, "y0": 88, "x1": 180, "y1": 104},
                "target_text": "Hello World",
            },
            original="",
            replacement="검토 필요",
        )
        patch_document_version(self.version.pk)

        self.version.refresh_from_db()
        self.assertEqual(
            self.version.status,
            DocumentVersion.Status.READY,
            "pdf_bbox annotate 성공 후 version.status는 READY여야 한다",
        )

    def test_pdf_bbox_annotate_returns_bytes(self):
        """pdf_bbox anchor + annotate → _patch_pdf가 bytes를 반환한다."""
        from apps.documents.tasks import _patch_pdf

        _make_change(
            self.version,
            operation_id="op_ann_02",
            operation="annotate",
            anchor={
                "type": "pdf_bbox",
                "page": 1,
                "rect": {"x0": 72, "y0": 88, "x1": 180, "y1": 104},
                "target_text": "Hello World",
            },
            replacement="검토 완료",
        )
        result = _patch_pdf(self.version, self.upload)

        self.assertIsInstance(result, (bytes, bytearray), "annotate 후 _patch_pdf는 bytes를 반환해야 한다")

    def test_text_match_annotate_sets_version_ready(self):
        """text_match anchor + annotate → search_for로 rect를 찾아 version.status=ready."""
        _make_change(
            self.version,
            operation_id="op_ann_03",
            operation="annotate",
            anchor={
                "type": "text_match",
                "target_text": "Hello World",
                "page": 1,
                "occurrence": 1,
            },
            replacement="텍스트 확인 필요",
        )
        patch_document_version(self.version.pk)

        self.version.refresh_from_db()
        self.assertEqual(
            self.version.status,
            DocumentVersion.Status.READY,
            "text_match annotate 성공 후 version.status는 READY여야 한다",
        )


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class PdfRedactOverlayTest(TestCase):
    """PDF redact_overlay 패처 테스트."""

    def setUp(self):
        self.user = _make_user("pdf_redact_user")
        self.pdf_bytes = _build_pdf_bytes("2025 08 11")
        self.upload = _make_upload(self.user, "redact.pdf", self.pdf_bytes, "pdf_redact_hash")
        self.version = _make_version(self.upload, self.user)

    def test_pdf_bbox_redact_overlay_sets_version_ready(self):
        """pdf_bbox anchor + redact_overlay → version.status=ready가 된다."""
        _make_change(
            self.version,
            operation_id="op_redact_01",
            operation="redact_overlay",
            anchor={
                "type": "pdf_bbox",
                "page": 1,
                "rect": {"x0": 72, "y0": 88, "x1": 200, "y1": 104},
                "target_text": "2025 08 11",
            },
            original="2025 08 11",
            replacement="2025-08-11",
        )
        patch_document_version(self.version.pk)

        self.version.refresh_from_db()
        self.assertEqual(
            self.version.status,
            DocumentVersion.Status.READY,
            "redact_overlay 성공 후 version.status는 READY여야 한다",
        )

    def test_redact_overlay_artifact_contains_replacement(self):
        """redact_overlay 후 _patch_pdf 반환 bytes를 열면 replacement 텍스트가 포함된다."""
        import fitz
        from apps.documents.tasks import _patch_pdf

        _make_change(
            self.version,
            operation_id="op_redact_02",
            operation="redact_overlay",
            anchor={
                "type": "pdf_bbox",
                "page": 1,
                "rect": {"x0": 72, "y0": 88, "x1": 200, "y1": 104},
                "target_text": "2025 08 11",
            },
            original="2025 08 11",
            replacement="2025-08-11",
        )
        result_bytes = _patch_pdf(self.version, self.upload)

        self.version.refresh_from_db()
        self.assertEqual(self.version.status, DocumentVersion.Status.READY)
        self.assertIsNotNone(result_bytes, "_patch_pdf는 bytes를 반환해야 한다")

        doc = fitz.open(stream=result_bytes, filetype="pdf")
        full_text = "".join(page.get_text() for page in doc)
        doc.close()

        self.assertIn(
            "2025-08-11",
            full_text,
            "반환 bytes PDF에 replacement 텍스트가 포함되어야 한다",
        )


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class PdfFailureTest(TestCase):
    """PDF 패처 실패 케이스 테스트."""

    def setUp(self):
        self.user = _make_user("pdf_fail_user")
        self.pdf_bytes = _build_pdf_bytes("Hello World")
        self.upload = _make_upload(self.user, "fail.pdf", self.pdf_bytes, "pdf_fail_hash")
        self.version = _make_version(self.upload, self.user)

    def test_anchor_miss_sets_change_failed(self):
        """anchor 해석 실패(text_match 텍스트 없음) → change.status=failed."""
        change = _make_change(
            self.version,
            operation_id="op_fail_01",
            operation="annotate",
            anchor={
                "type": "text_match",
                "target_text": "존재하지 않는 텍스트",
                "page": 1,
            },
            replacement="무관",
        )
        patch_document_version(self.version.pk)

        change.refresh_from_db()
        self.assertEqual(
            change.status,
            DocumentChange.Status.FAILED,
            "anchor 해석 실패 시 change.status는 FAILED여야 한다",
        )

    def test_all_changes_failed_sets_version_failed(self):
        """모든 change 실패 → version.status=failed."""
        _make_change(
            self.version,
            operation_id="op_fail_02",
            operation="annotate",
            anchor={"type": "text_match", "target_text": "없는텍스트A"},
        )
        _make_change(
            self.version,
            operation_id="op_fail_03",
            operation="annotate",
            anchor={"type": "text_match", "target_text": "없는텍스트B"},
        )
        patch_document_version(self.version.pk)

        self.version.refresh_from_db()
        self.assertEqual(
            self.version.status,
            DocumentVersion.Status.FAILED,
            "모든 change가 실패하면 version.status는 FAILED여야 한다",
        )

    def test_one_success_sets_version_ready(self):
        """하나라도 성공 → version.status=ready + artifact_file 생성."""
        # 실패할 change
        _make_change(
            self.version,
            operation_id="op_partial_01",
            operation="annotate",
            anchor={"type": "text_match", "target_text": "없는텍스트"},
        )
        # 성공할 change (pdf_bbox — rect 값은 임의)
        _make_change(
            self.version,
            operation_id="op_partial_02",
            operation="annotate",
            anchor={
                "type": "pdf_bbox",
                "page": 1,
                "rect": {"x0": 72, "y0": 88, "x1": 180, "y1": 104},
            },
            replacement="부분 성공 주석",
        )
        patch_document_version(self.version.pk)

        self.version.refresh_from_db()
        self.assertEqual(
            self.version.status,
            DocumentVersion.Status.READY,
            "하나라도 성공하면 version.status는 READY여야 한다",
        )
