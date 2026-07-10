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
  8. DOCX text_match 다중 매치 → 자동 반영하지 않고 NEEDS_CONFIRMATION으로 멈춤
     (design v1 10.1절 — "DOCX 다중 매치 침묵 처리 수정", code=ambiguous_anchor)
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


def _build_docx_bytes_multi(paragraph_texts: list[str]) -> bytes:
    """여러 단락으로 구성된 DOCX 바이트를 생성한다 (다중 매치 테스트용)."""
    from docx import Document
    doc = Document()
    for text in paragraph_texts:
        doc.add_paragraph(text)
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
        """패치 후 render_docx 반환 bytes를 열면 replacement 텍스트가 포함된다."""
        from docx import Document
        from apps.documents.patcher import collect_applied_changes, persist_patch_result, render_docx

        _make_change(
            self.version,
            operation_id="op_docx_03",
            operation="replace_text",
            anchor={"type": "text_match", "text_match": "2026년 1월 계약서입니다."},
            original="2026년 1월 계약서입니다.",
            replacement="2026년 2월 수정 계약서입니다.",
        )
        changes = collect_applied_changes(self.version, operations=["replace_text"])
        with self.upload.file.open("rb") as f:
            original_bytes = f.read()
        patch_result = render_docx(original_bytes, changes)
        persist_patch_result(self.version, patch_result, "docx", changes)

        self.version.refresh_from_db()
        self.assertEqual(self.version.status, DocumentVersion.Status.READY)

        result_bytes = patch_result.output_bytes
        self.assertGreater(len(result_bytes), 0, "render_docx는 bytes를 반환해야 한다")
        doc = Document(io.BytesIO(result_bytes))
        full_text = "\n".join(p.text for p in doc.paragraphs)
        self.assertIn(
            "2026년 2월 수정 계약서입니다.",
            full_text,
            "반환 bytes에 replacement 텍스트가 포함되어야 한다",
        )


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class DocxAmbiguousMatchTest(TestCase):
    """
    [버그 수정] DOCX replace_text 다중 매치 → NEEDS_CONFIRMATION 테스트 (design v1 10.1절).

    수정 전에는 같은 문구(text_match)가 문서에 두 번 이상 나와도 첫 번째 단락만
    조용히 수정하고 성공으로 처리했다 — PDF(AnchorResolver AMBIGUOUS)처럼
    "매치 2개 이상이면 자동 반영하지 않고 멈춤"이어야 한다.
    """

    def setUp(self):
        self.user = _make_user("docx_ambiguous_user")

    def _make_docx_version(self, paragraphs, hash_val):
        docx_bytes = _build_docx_bytes_multi(paragraphs)
        upload = _make_upload(
            self.user, "docx", "ambiguous.docx", docx_bytes, hash_val=hash_val
        )
        return upload, _make_version(upload, self.user)

    def test_duplicate_across_paragraphs_returns_needs_confirmation_item(self):
        """서로 다른 단락에 같은 text_match가 2개 → needs_confirmation_items, 변형·artifact 없음."""
        from apps.documents.patcher import collect_applied_changes, render_docx

        upload, version = self._make_docx_version(
            ["계약금액 1,000원", "비고: 계약금액은 부가세 포함"],
            hash_val="docx_ambiguous_render_hash",
        )
        _make_change(
            version,
            operation_id="op_docx_dup_01",
            operation="replace_text",
            anchor={"type": "text_match", "text_match": "계약금액"},
            original="계약금액",
            replacement="총계약금액",
        )
        changes = collect_applied_changes(version, operations=["replace_text"])
        with upload.file.open("rb") as f:
            original_bytes = f.read()
        result = render_docx(original_bytes, changes)

        self.assertEqual(result.applied_ids, [], "다중 매치는 자동 반영되면 안 된다")
        self.assertEqual(result.failed_items, [])
        self.assertEqual(len(result.needs_confirmation_items), 1)
        item = result.needs_confirmation_items[0]
        self.assertEqual(item["operation_id"], "op_docx_dup_01")
        self.assertEqual(
            item.get("code"),
            "ambiguous_anchor",
            "다중 매치 항목에는 안정된 실패 사유 코드 ambiguous_anchor가 있어야 한다 (design v1 8절)",
        )
        self.assertEqual(result.output_bytes, b"", "모호한 항목만 있으면 artifact bytes가 생성되면 안 된다")

    def test_duplicate_in_same_paragraph_is_also_ambiguous(self):
        """[경계] 한 단락 안에 text_match가 2번 나와도 동일하게 NEEDS_CONFIRMATION이다."""
        from apps.documents.patcher import collect_applied_changes, render_docx

        upload, version = self._make_docx_version(
            ["금액 100원 그리고 금액 200원"],
            hash_val="docx_ambiguous_same_para_hash",
        )
        _make_change(
            version,
            operation_id="op_docx_dup_02",
            operation="replace_text",
            anchor={"type": "text_match", "text_match": "금액"},
            original="금액",
            replacement="합계금액",
        )
        changes = collect_applied_changes(version, operations=["replace_text"])
        with upload.file.open("rb") as f:
            original_bytes = f.read()
        result = render_docx(original_bytes, changes)

        self.assertEqual(result.applied_ids, [])
        self.assertEqual(len(result.needs_confirmation_items), 1)
        self.assertEqual(result.needs_confirmation_items[0].get("code"), "ambiguous_anchor")

    def test_duplicate_match_via_task_sets_needs_confirmation_status(self):
        """task 경로: change/version 모두 NEEDS_CONFIRMATION, artifact 없음, change_ids 채워짐."""
        upload, version = self._make_docx_version(
            ["계약금액 1,000원", "비고: 계약금액은 부가세 포함"],
            hash_val="docx_ambiguous_task_hash",
        )
        change = _make_change(
            version,
            operation_id="op_docx_dup_task",
            operation="replace_text",
            anchor={"type": "text_match", "text_match": "계약금액"},
            original="계약금액",
            replacement="총계약금액",
        )
        patch_document_version(version.pk)

        change.refresh_from_db()
        version.refresh_from_db()
        self.assertEqual(
            change.status,
            DocumentChange.Status.NEEDS_CONFIRMATION,
            "다중 매치 change는 FAILED가 아니라 NEEDS_CONFIRMATION이어야 한다",
        )
        self.assertEqual(version.status, DocumentVersion.Status.NEEDS_CONFIRMATION)
        self.assertFalse(version.artifact_file, "NEEDS_CONFIRMATION이면 artifact가 저장되면 안 된다")
        self.assertEqual(version.needs_confirmation_change_ids, ["op_docx_dup_task"])

    def test_mixed_resolved_and_ambiguous_keeps_partial_success(self):
        """유일 매치 + 다중 매치가 섞이면 유일 매치만 반영되고 version은 READY(부분 성공)."""
        upload, version = self._make_docx_version(
            ["갑: 주식회사 한빛", "계약금액 1,000원", "비고: 계약금액은 부가세 포함"],
            hash_val="docx_ambiguous_mixed_hash",
        )
        resolved_change = _make_change(
            version,
            operation_id="op_docx_mixed_resolved",
            operation="replace_text",
            anchor={"type": "text_match", "text_match": "주식회사 한빛"},
            original="주식회사 한빛",
            replacement="주식회사 두빛",
        )
        ambiguous_change = _make_change(
            version,
            operation_id="op_docx_mixed_ambiguous",
            operation="replace_text",
            anchor={"type": "text_match", "text_match": "계약금액"},
            original="계약금액",
            replacement="총계약금액",
        )
        patch_document_version(version.pk)

        resolved_change.refresh_from_db()
        ambiguous_change.refresh_from_db()
        version.refresh_from_db()

        self.assertEqual(resolved_change.status, DocumentChange.Status.APPLIED)
        self.assertEqual(ambiguous_change.status, DocumentChange.Status.NEEDS_CONFIRMATION)
        self.assertEqual(version.status, DocumentVersion.Status.READY)
        self.assertIn("op_docx_mixed_resolved", version.applied_change_ids)
        self.assertNotIn("op_docx_mixed_ambiguous", version.applied_change_ids)
        self.assertEqual(version.needs_confirmation_change_ids, ["op_docx_mixed_ambiguous"])

        # 부분 성공 artifact에는 유일 매치의 replacement만 반영되고,
        # 모호한 항목의 원문은 두 곳 모두 그대로 남아 있어야 한다.
        from docx import Document
        with version.artifact_file.open("rb") as f:
            doc = Document(io.BytesIO(f.read()))
        full_text = "\n".join(p.text for p in doc.paragraphs)
        self.assertIn("주식회사 두빛", full_text)
        self.assertEqual(full_text.count("계약금액"), 2, "모호한 항목은 어느 쪽도 변형되면 안 된다")

    def test_empty_text_match_produces_failed_item(self):
        """[경계] 빈 text_match는 임의 위치 삽입 대신 failed_items로 실패해야 한다."""
        from apps.documents.patcher import collect_applied_changes, render_docx

        upload, version = self._make_docx_version(
            ["계약금액 1,000원"],
            hash_val="docx_ambiguous_empty_hash",
        )
        _make_change(
            version,
            operation_id="op_docx_empty_match",
            operation="replace_text",
            anchor={"type": "text_match", "text_match": ""},
            original="",
            replacement="무관",
        )
        changes = collect_applied_changes(version, operations=["replace_text"])
        with upload.file.open("rb") as f:
            original_bytes = f.read()
        result = render_docx(original_bytes, changes)

        self.assertEqual(result.applied_ids, [])
        self.assertEqual(result.needs_confirmation_items, [])
        self.assertEqual(len(result.failed_items), 1)
        self.assertEqual(result.failed_items[0]["operation_id"], "op_docx_empty_match")


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
        """패치 후 render_pptx 반환 bytes를 열면 replacement 텍스트가 포함된다."""
        from pptx import Presentation
        from apps.documents.patcher import collect_applied_changes, persist_patch_result, render_pptx

        _make_change(
            self.version,
            operation_id="op_pptx_03",
            operation="replace_text",
            anchor={"type": "slide_shape", "slide_index": 0, "shape_index": 0, "text_match": "2026년 1분기 실적 보고"},
            original="2026년 1분기 실적 보고",
            replacement="2026년 2분기 실적 보고",
        )
        changes = collect_applied_changes(self.version, operations=["replace_text"])
        with self.upload.file.open("rb") as f:
            original_bytes = f.read()
        patch_result = render_pptx(original_bytes, changes)
        persist_patch_result(self.version, patch_result, "pptx", changes)

        self.version.refresh_from_db()
        self.assertEqual(self.version.status, DocumentVersion.Status.READY)

        result_bytes = patch_result.output_bytes
        self.assertGreater(len(result_bytes), 0, "render_pptx는 bytes를 반환해야 한다")
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


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class TextAnchorContractKeyTest(TestCase):
    """
    [버그 수정] text 계열 anchor 계약 키(target_text) 테스트.

    patch-plan-schema-v0 7.2절과 LLM 프롬프트(prompts/patch_plan.py)는 text_match
    anchor의 대상 키를 "target_text"로 정의하는데, 기존 DOCX/PPTX patcher는
    "text_match" 키만 읽었다 — 실제 LLM/규칙 기반 플랜의 anchor로는 대상을 항상
    빈 문자열로 읽어 동작하지 않았다(계약-구현 불일치). PDF resolver는 이미
    target_text를 읽으므로 DOCX/PPTX만 맞춘다.
    """

    def setUp(self):
        self.user = _make_user("anchor_contract_user")

    def test_docx_target_text_key_unique_match_applies(self):
        """계약 키 target_text로 유일 매치가 정상 교체된다."""
        from apps.documents.patcher import collect_applied_changes, render_docx
        from docx import Document

        docx_bytes = _build_docx_bytes_multi(["계약금액 1,000원"])
        upload = _make_upload(
            self.user, "docx", "contract_key.docx", docx_bytes, hash_val="docx_contract_key_hash"
        )
        version = _make_version(upload, self.user)
        _make_change(
            version,
            operation_id="op_docx_contract_key",
            operation="replace_text",
            anchor={"type": "text_match", "target_text": "계약금액", "occurrence": 1},
            original="계약금액",
            replacement="총계약금액",
        )
        changes = collect_applied_changes(version, operations=["replace_text"])
        with upload.file.open("rb") as f:
            original_bytes = f.read()
        result = render_docx(original_bytes, changes)

        self.assertEqual(
            result.applied_ids,
            ["op_docx_contract_key"],
            "계약 키 target_text anchor로도 교체가 적용되어야 한다",
        )
        self.assertEqual(result.failed_items, [])
        doc = Document(io.BytesIO(result.output_bytes))
        full_text = "\n".join(p.text for p in doc.paragraphs)
        self.assertIn("총계약금액", full_text)

    def test_docx_target_text_key_duplicate_stops_with_needs_confirmation(self):
        """계약 키 target_text에서도 다중 매치는 NEEDS_CONFIRMATION으로 멈춘다."""
        from apps.documents.patcher import collect_applied_changes, render_docx

        docx_bytes = _build_docx_bytes_multi(
            ["계약금액 1,000원", "비고: 계약금액은 부가세 포함"]
        )
        upload = _make_upload(
            self.user, "docx", "contract_key_dup.docx", docx_bytes,
            hash_val="docx_contract_key_dup_hash",
        )
        version = _make_version(upload, self.user)
        _make_change(
            version,
            operation_id="op_docx_contract_dup",
            operation="replace_text",
            anchor={"type": "text_match", "target_text": "계약금액"},
            original="계약금액",
            replacement="총계약금액",
        )
        changes = collect_applied_changes(version, operations=["replace_text"])
        with upload.file.open("rb") as f:
            original_bytes = f.read()
        result = render_docx(original_bytes, changes)

        self.assertEqual(result.applied_ids, [])
        self.assertEqual(len(result.needs_confirmation_items), 1)
        self.assertEqual(result.needs_confirmation_items[0].get("code"), "ambiguous_anchor")

    def test_pptx_target_text_key_applies_without_prepend_corruption(self):
        """
        [회귀] PPTX도 계약 키 target_text를 읽어야 한다 — 기존에는 빈 문자열로
        읽혀 첫 단락 맨 앞에 replacement가 침묵 삽입되는 오염이 발생했다.
        """
        from apps.documents.patcher import collect_applied_changes, render_pptx
        from pptx import Presentation

        pptx_bytes = _build_pptx_bytes("발표자료 v1")
        upload = _make_upload(
            self.user, "pptx", "contract_key.pptx", pptx_bytes, hash_val="pptx_contract_key_hash"
        )
        version = _make_version(upload, self.user)
        _make_change(
            version,
            operation_id="op_pptx_contract_key",
            operation="replace_text",
            anchor={"type": "text_match", "target_text": "v1", "slide_index": 0, "shape_index": 0},
            original="v1",
            replacement="v2",
        )
        changes = collect_applied_changes(version, operations=["replace_text"])
        with upload.file.open("rb") as f:
            original_bytes = f.read()
        result = render_pptx(original_bytes, changes)

        self.assertEqual(result.applied_ids, ["op_pptx_contract_key"])
        prs = Presentation(io.BytesIO(result.output_bytes))
        texts = [
            para.text
            for slide in prs.slides
            for shape in slide.shapes
            if shape.has_text_frame
            for para in shape.text_frame.paragraphs
        ]
        joined = "\n".join(texts)
        self.assertIn("발표자료 v2", joined, "target_text 위치가 정확히 교체되어야 한다")
        self.assertNotIn("v2발표자료", joined, "맨 앞 침묵 삽입 오염이 있어서는 안 된다")

    def test_pptx_empty_target_text_fails_explicitly(self):
        """[경계] 대상 키가 모두 비어 있으면 침묵 삽입 대신 failed_items로 실패한다."""
        from apps.documents.patcher import collect_applied_changes, render_pptx

        pptx_bytes = _build_pptx_bytes("발표자료 v1")
        upload = _make_upload(
            self.user, "pptx", "contract_key_empty.pptx", pptx_bytes,
            hash_val="pptx_contract_key_empty_hash",
        )
        version = _make_version(upload, self.user)
        _make_change(
            version,
            operation_id="op_pptx_empty_key",
            operation="replace_text",
            anchor={"type": "text_match", "slide_index": 0, "shape_index": 0},
            original="",
            replacement="오염텍스트",
        )
        changes = collect_applied_changes(version, operations=["replace_text"])
        with upload.file.open("rb") as f:
            original_bytes = f.read()
        result = render_pptx(original_bytes, changes)

        self.assertEqual(result.applied_ids, [], "빈 대상 키가 applied로 처리되면 안 된다")
        self.assertEqual(len(result.failed_items), 1)
        self.assertEqual(result.failed_items[0]["operation_id"], "op_pptx_empty_key")
