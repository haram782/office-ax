"""
DOCX / PPTX replace_text 패처 테스트.

커버 범위:
  patch_document_version Celery 태스크 (동기 직접 호출)
  - DOCX: replace_text 단락 반영, text_match 불일치 → change.failed, artifact 저장 + version.ready
  - PPTX: replace_text 셰이프 텍스트 반영, shape_index OOB → change.failed, artifact 저장 + version.ready
  - 공통: 지원하지 않는 source_type → version.status=failed + error_message 포함

테스트 케이스:
  1. DOCX replace_text 반영 → version.status=ready, artifact_file 저장됨
  2. DOCX text_match 불일치 → change.status=failed, version.status=failed
  3. DOCX 정상 패치 후 artifact 읽으면 replacement 텍스트가 포함됨
  4. PPTX replace_text 반영 → version.status=ready, artifact_file 저장됨
  5. PPTX shape_index 범위 초과 → change.status=failed, version.status=failed
  6. PPTX 정상 패치 후 artifact 읽으면 replacement 텍스트가 포함됨
  7. 지원하지 않는 source_type(hwp) → version.status=failed, error_message에 'hwp' 포함
"""
import io
import os
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

# 테스트용 임시 MEDIA_ROOT (파일 저장 격리)
TEMP_MEDIA = tempfile.mkdtemp()


def teardown_module(_module):
    """모듈 종료 시 임시 디렉터리 정리."""
    import shutil
    shutil.rmtree(TEMP_MEDIA, ignore_errors=True)


# ── 헬퍼 함수 ─────────────────────────────────────────────────────────────────


def _make_user(username):
    return User.objects.create_user(username=username, password="pw")


def _make_upload(user, source_type, filename, file_bytes, hash_val=None):
    """UploadLog와 임시 파일을 함께 생성한다."""
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


def _make_version(upload, user, status=DocumentVersion.Status.DRAFT, version_number=2):
    return DocumentVersion.objects.create(
        upload_log=upload,
        version_number=version_number,
        status=status,
        label="draft",
        created_by=user,
    )


def _make_change(version, operation_id, operation, anchor, original, replacement,
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


def _build_docx_bytes(paragraph_text: str) -> bytes:
    """지정 텍스트가 포함된 단락 하나짜리 DOCX 바이트를 생성한다."""
    from docx import Document
    doc = Document()
    doc.add_paragraph(paragraph_text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _build_pptx_bytes(shape_text: str) -> bytes:
    """첫 번째 슬라이드 첫 번째 셰이프에 텍스트를 넣은 PPTX 바이트를 생성한다."""
    from pptx import Presentation
    from pptx.util import Inches
    prs = Presentation()
    blank_layout = prs.slide_layouts[6]  # 빈 레이아웃
    slide = prs.slides.add_slide(blank_layout)
    txBox = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1))
    txBox.text_frame.text = shape_text
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


# ── 테스트 클래스 ─────────────────────────────────────────────────────────────


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class DocxPatcherTest(TestCase):
    """DOCX replace_text 패처 테스트."""

    def setUp(self):
        self.user = _make_user("docx_user")
        docx_bytes = _build_docx_bytes("2026년 1월 계약서입니다.")
        self.upload = _make_upload(
            self.user, "docx", "sample.docx", docx_bytes, hash_val="docx_test_hash"
        )
        self.version = _make_version(self.upload, self.user)

    def test_replace_text_sets_version_ready(self):
        """replace_text 변경이 반영되면 version.status=ready가 된다."""
        _make_change(
            self.version,
            operation_id="op_docx_01",
            operation="replace_text",
            anchor={"type": "text_match", "text_match": "2026년 1월"},
            original="2026년 1월",
            replacement="2026년 2월",
        )
        patch_document_version(self.version.pk)

        self.version.refresh_from_db()
        self.assertEqual(
            self.version.status,
            DocumentVersion.Status.READY,
            "replace_text 반영 후 version.status는 READY여야 한다",
        )

    def test_text_match_mismatch_sets_change_failed(self):
        """text_match가 문서에 없으면 change.status=failed가 된다."""
        change = _make_change(
            self.version,
            operation_id="op_docx_02",
            operation="replace_text",
            anchor={"type": "text_match", "text_match": "존재하지 않는 텍스트"},
            original="존재하지 않는 텍스트",
            replacement="무관",
        )
        patch_document_version(self.version.pk)

        change.refresh_from_db()
        self.assertEqual(
            change.status,
            DocumentChange.Status.FAILED,
            "text_match 불일치 시 change.status는 FAILED여야 한다",
        )

        self.version.refresh_from_db()
        self.assertEqual(
            self.version.status,
            DocumentVersion.Status.FAILED,
            "모든 change가 실패하면 version.status는 FAILED여야 한다",
        )

    def test_artifact_contains_replacement_text(self):
        """패치 후 _patch_docx 반환 bytes를 열면 replacement 텍스트가 포함된다."""
        from docx import Document
        from apps.documents.tasks import _patch_docx

        _make_change(
            self.version,
            operation_id="op_docx_03",
            operation="replace_text",
            anchor={"type": "text_match", "text_match": "2026년 1월 계약서입니다."},
            original="2026년 1월 계약서입니다.",
            replacement="2026년 2월 수정 계약서입니다.",
        )
        result_bytes = _patch_docx(self.version, self.upload)

        self.version.refresh_from_db()
        self.assertEqual(self.version.status, DocumentVersion.Status.READY)

        self.assertIsNotNone(result_bytes, "_patch_docx는 bytes를 반환해야 한다")
        doc = Document(io.BytesIO(result_bytes))
        full_text = "\n".join(p.text for p in doc.paragraphs)
        self.assertIn(
            "2026년 2월 수정 계약서입니다.",
            full_text,
            "반환 bytes에 replacement 텍스트가 포함되어야 한다",
        )


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class PptxPatcherTest(TestCase):
    """PPTX replace_text 패처 테스트."""

    def setUp(self):
        self.user = _make_user("pptx_user")
        pptx_bytes = _build_pptx_bytes("2026년 1분기 실적 보고")
        self.upload = _make_upload(
            self.user, "pptx", "sample.pptx", pptx_bytes, hash_val="pptx_test_hash"
        )
        self.version = _make_version(self.upload, self.user)

    def test_replace_text_sets_version_ready(self):
        """replace_text 변경이 반영되면 version.status=ready가 된다."""
        _make_change(
            self.version,
            operation_id="op_pptx_01",
            operation="replace_text",
            anchor={"type": "slide_shape", "slide_index": 0, "shape_index": 0, "text_match": "2026년 1분기"},
            original="2026년 1분기",
            replacement="2026년 2분기",
        )
        patch_document_version(self.version.pk)

        self.version.refresh_from_db()
        self.assertEqual(
            self.version.status,
            DocumentVersion.Status.READY,
            "replace_text 반영 후 version.status는 READY여야 한다",
        )

    def test_shape_index_out_of_bounds_sets_change_failed(self):
        """shape_index가 슬라이드 셰이프 범위를 벗어나면 change.status=failed가 된다."""
        change = _make_change(
            self.version,
            operation_id="op_pptx_02",
            operation="replace_text",
            anchor={"type": "slide_shape", "slide_index": 0, "shape_index": 999, "text_match": "없음"},
            original="없음",
            replacement="무관",
        )
        patch_document_version(self.version.pk)

        change.refresh_from_db()
        self.assertEqual(
            change.status,
            DocumentChange.Status.FAILED,
            "shape_index OOB 시 change.status는 FAILED여야 한다",
        )

        self.version.refresh_from_db()
        self.assertEqual(
            self.version.status,
            DocumentVersion.Status.FAILED,
            "모든 change가 실패하면 version.status는 FAILED여야 한다",
        )

    def test_artifact_contains_replacement_text(self):
        """패치 후 _patch_pptx 반환 bytes를 열면 replacement 텍스트가 포함된다."""
        from pptx import Presentation
        from apps.documents.tasks import _patch_pptx

        _make_change(
            self.version,
            operation_id="op_pptx_03",
            operation="replace_text",
            anchor={"type": "slide_shape", "slide_index": 0, "shape_index": 0, "text_match": "2026년 1분기 실적 보고"},
            original="2026년 1분기 실적 보고",
            replacement="2026년 2분기 실적 보고",
        )
        result_bytes = _patch_pptx(self.version, self.upload)

        self.version.refresh_from_db()
        self.assertEqual(self.version.status, DocumentVersion.Status.READY)

        self.assertIsNotNone(result_bytes, "_patch_pptx는 bytes를 반환해야 한다")
        prs = Presentation(io.BytesIO(result_bytes))
        texts = []
        for slide in prs.slides:
            for shape in slide.shapes:
                if shape.has_text_frame:
                    texts.append(shape.text_frame.text)
        self.assertIn(
            "2026년 2분기 실적 보고",
            " ".join(texts),
            "반환 bytes에 replacement 텍스트가 포함되어야 한다",
        )


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class UnsupportedFormatTest(TestCase):
    """지원하지 않는 source_type → version.status=failed 테스트."""

    def setUp(self):
        self.user = _make_user("unsupported_user")

    def test_image_source_type_sets_version_failed(self):
        """
        source_type=image(미지원 포맷) → version.status=failed이고
        error_message에 포맷명이 포함된다.

        HWP는 별도 patcher가 구현되어 지원 포맷이므로 image로 대체한다.
        """
        fs, _ = FileStructure.objects.get_or_create(
            hash="image_test_hash",
            defaults={"source_type": "image", "column_schema": []},
        )
        upload = UploadLog.objects.create(
            user=self.user,
            file_structure=fs,
            original_filename="sample.png",
            status=UploadLog.Status.DONE,
        )
        # 최소 크기의 더미 파일 저장 (파일 존재 확인 통과용)
        upload.file.save("sample.png", ContentFile(b"dummy"), save=True)

        version = _make_version(upload, self.user)
        patch_document_version(version.pk)

        version.refresh_from_db()
        self.assertEqual(
            version.status,
            DocumentVersion.Status.FAILED,
            "지원하지 않는 포맷은 version.status=FAILED여야 한다",
        )
        self.assertIn(
            "image",
            version.error_message,
            "error_message에 지원하지 않는 포맷 이름이 포함되어야 한다",
        )
