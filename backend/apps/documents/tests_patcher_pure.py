"""
patcher.py 순수 함수 테스트.

render_* 함수는 DB/storage I/O가 없는 순수 변환 함수임을 증명한다.
테스트 안에서 DocumentChange.objects.* 같은 DB 접근이 전혀 없다.

커버 범위:
  render_xlsx   — happy / 원본 불일치 / 시트 없음
  render_docx   — happy / 텍스트 불일치
  render_pptx   — happy (슬라이드 텍스트 교체)
  render_hwp    — happy(mock) / subprocess 실패(mock)
  collect_applied_changes  — applied 필터, operation 타입 필터
  persist_patch_result     — applied 있을 때 / applied 없을 때
"""
import io
import types
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch as mock_patch

import openpyxl
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TestCase, override_settings

from apps.documents.patcher import (
    PatchResult,
    collect_applied_changes,
    persist_patch_result,
    render_docx,
    render_hwp,
    render_pptx,
    render_xlsx,
)

User = get_user_model()

import tempfile
import shutil

TEMP_MEDIA = tempfile.mkdtemp(prefix="office_ax_patcher_pure_")


def teardown_module(_module):
    shutil.rmtree(TEMP_MEDIA, ignore_errors=True)


# ── 인메모리 파일 생성 헬퍼 ───────────────────────────────────────────────────

def _xlsx_bytes(sheet: str = "Sheet1", data: dict | None = None) -> bytes:
    """인메모리 XLSX 바이트 생성."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    if data:
        for ref, val in data.items():
            ws[ref] = val
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _docx_bytes(paragraph_text: str) -> bytes:
    """단락 하나짜리 DOCX 바이트 생성."""
    from docx import Document
    doc = Document()
    doc.add_paragraph(paragraph_text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _pptx_bytes(text: str) -> bytes:
    """첫 번째 슬라이드에 텍스트박스가 있는 PPTX 바이트 생성."""
    from pptx import Presentation
    from pptx.util import Inches
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    txBox = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1))
    txBox.text_frame.text = text
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _change(**kwargs) -> SimpleNamespace:
    """DB 없이 change 속성을 담은 SimpleNamespace 생성. render_* 순수 함수에 직접 전달한다."""
    defaults = {
        "operation_id": "op_test",
        "original": "",
        "replacement": "",
        "anchor": {},
        "operation": "replace_cell",
        "reason": "",
        "patch": {},
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ── render_xlsx ──────────────────────────────────────────────────────────────

class RenderXlsxPureTest(unittest.TestCase):
    """render_xlsx: DB 없이 bytes in → PatchResult out."""

    def _run(self, original_bytes, changes):
        return render_xlsx(original_bytes, changes)

    def test_happy_path_applies_cell_replacement(self):
        """A2="20260101" → replacement="2026-01-01" → applied_ids에 포함, XLSX에 반영."""
        original = _xlsx_bytes("Sheet1", {"A2": "20260101"})
        c = _change(
            operation_id="op_xlsx_ok",
            original="20260101",
            replacement="2026-01-01",
            anchor={"type": "cell", "sheet": "Sheet1", "cell": "A2"},
        )

        result = self._run(original, [c])

        self.assertEqual(result.applied_ids, ["op_xlsx_ok"])
        self.assertEqual(result.failed_items, [])
        # 출력 XLSX에서 셀 값 확인
        wb = openpyxl.load_workbook(io.BytesIO(result.output_bytes))
        self.assertEqual(str(wb["Sheet1"]["A2"].value), "2026-01-01")

    def test_original_mismatch_produces_failed_item(self):
        """원본 값 불일치 → failed_items에 기록, applied_ids=[], output_bytes=b""."""
        original = _xlsx_bytes("Sheet1", {"A2": "실제값"})
        c = _change(
            operation_id="op_xlsx_mismatch",
            original="WRONG",
            replacement="새값",
            anchor={"type": "cell", "sheet": "Sheet1", "cell": "A2"},
        )

        result = self._run(original, [c])

        self.assertEqual(result.applied_ids, [])
        self.assertEqual(len(result.failed_items), 1)
        self.assertEqual(result.failed_items[0]["operation_id"], "op_xlsx_mismatch")
        self.assertEqual(result.output_bytes, b"")

    def test_missing_sheet_produces_failed_item(self):
        """anchor.sheet가 존재하지 않는 시트 → failed_items에 기록."""
        original = _xlsx_bytes("Sheet1", {})
        c = _change(
            operation_id="op_xlsx_nosheet",
            original="x",
            replacement="y",
            anchor={"type": "cell", "sheet": "NoSuchSheet", "cell": "A1"},
        )

        result = self._run(original, [c])

        self.assertEqual(result.applied_ids, [])
        self.assertEqual(len(result.failed_items), 1)
        self.assertEqual(result.failed_items[0]["operation_id"], "op_xlsx_nosheet")

    def test_partial_success_returns_output_bytes(self):
        """성공 1건 + 실패 1건 → applied_ids에 성공만, output_bytes가 비어있지 않음."""
        original = _xlsx_bytes("Sheet1", {"A2": "원본A", "B2": "원본B"})
        ok = _change(
            operation_id="op_ok",
            original="원본A",
            replacement="새A",
            anchor={"type": "cell", "sheet": "Sheet1", "cell": "A2"},
        )
        fail = _change(
            operation_id="op_fail",
            original="WRONG",
            replacement="새B",
            anchor={"type": "cell", "sheet": "Sheet1", "cell": "B2"},
        )

        result = self._run(original, [ok, fail])

        self.assertEqual(result.applied_ids, ["op_ok"])
        self.assertEqual(len(result.failed_items), 1)
        self.assertGreater(len(result.output_bytes), 0)


# ── render_docx ──────────────────────────────────────────────────────────────

class RenderDocxPureTest(unittest.TestCase):
    """render_docx: DB 없이 bytes in → PatchResult out."""

    def test_happy_path_replaces_paragraph_text(self):
        """'안녕하세요'가 포함된 DOCX → replacement='반갑습니다' → applied."""
        original = _docx_bytes("안녕하세요 테스트")
        c = _change(
            operation_id="op_docx_ok",
            original="안녕하세요 테스트",
            replacement="반갑습니다",
            anchor={"type": "text_match", "text_match": "안녕하세요 테스트"},
            operation="replace_text",
        )

        result = render_docx(original, [c])

        self.assertEqual(result.applied_ids, ["op_docx_ok"])
        self.assertEqual(result.failed_items, [])
        # 출력 DOCX에서 텍스트 확인
        from docx import Document
        doc = Document(io.BytesIO(result.output_bytes))
        full_text = " ".join(p.text for p in doc.paragraphs)
        self.assertIn("반갑습니다", full_text)

    def test_text_not_found_produces_failed_item(self):
        """anchor의 text_match가 DOCX 단락에 없음 → failed_items에 기록."""
        original = _docx_bytes("전혀 다른 텍스트")
        c = _change(
            operation_id="op_docx_notfound",
            original="없는텍스트",
            replacement="새텍스트",
            anchor={"type": "text_match", "text_match": "없는텍스트"},
            operation="replace_text",
        )

        result = render_docx(original, [c])

        self.assertEqual(result.applied_ids, [])
        self.assertEqual(len(result.failed_items), 1)
        self.assertEqual(result.failed_items[0]["operation_id"], "op_docx_notfound")


# ── render_pptx ──────────────────────────────────────────────────────────────

class RenderPptxPureTest(unittest.TestCase):
    """render_pptx: DB 없이 bytes in → PatchResult out."""

    def test_happy_path_replaces_shape_text(self):
        """슬라이드 첫 셰이프의 텍스트 교체 → applied, 출력에 replacement 포함."""
        original = _pptx_bytes("슬라이드 원본")
        c = _change(
            operation_id="op_pptx_ok",
            original="슬라이드 원본",
            replacement="수정된 슬라이드",
            anchor={"type": "slide_shape", "slide_index": 0, "shape_index": 0,
                    "text_match": "슬라이드 원본"},
            operation="replace_text",
        )

        result = render_pptx(original, [c])

        self.assertEqual(result.applied_ids, ["op_pptx_ok"])
        self.assertEqual(result.failed_items, [])
        from pptx import Presentation
        prs = Presentation(io.BytesIO(result.output_bytes))
        texts = [
            shape.text
            for slide in prs.slides
            for shape in slide.shapes
            if shape.has_text_frame
        ]
        self.assertTrue(any("수정된 슬라이드" in t for t in texts))


# ── render_hwp (subprocess mock) ─────────────────────────────────────────────

class RenderHwpMockTest(unittest.TestCase):
    """render_hwp: subprocess를 mock해 PatchResult 반환 동작을 검증한다."""

    def _make_worker_output(self, applied: list, failed: list) -> MagicMock:
        mock = MagicMock()
        mock.returncode = 0
        import json as _json
        mock.stdout = _json.dumps({
            "applied": applied,
            "failed": failed,
            "output_b64": __import__("base64").b64encode(b"dummy hwp output").decode(),
        }).encode()
        mock.stderr = b""
        return mock

    @mock_patch("apps.documents.patcher.subprocess.run")
    def test_success_returns_patch_result_with_applied_ids(self, mock_run):
        """worker 성공 → PatchResult(applied_ids=[...], output_bytes=hwp bytes)."""
        mock_run.return_value = self._make_worker_output(["op_hwp_01"], [])
        c = _change(operation_id="op_hwp_01", original="11월", replacement="12월",
                    anchor={"type": "text_match", "target_text": "11월"},
                    operation="replace_text")

        result = render_hwp(b"dummy hwp input", [c])

        self.assertEqual(result.applied_ids, ["op_hwp_01"])
        self.assertEqual(result.failed_items, [])
        self.assertGreater(len(result.output_bytes), 0)

    @mock_patch("apps.documents.patcher.subprocess.run")
    def test_worker_nonzero_returncode_returns_all_failed(self, mock_run):
        """worker returncode != 0 → PatchResult(applied_ids=[], all changes in failed_items)."""
        failure_mock = MagicMock()
        failure_mock.returncode = 1
        failure_mock.stdout = b""
        failure_mock.stderr = b"Node error"
        mock_run.return_value = failure_mock

        c = _change(operation_id="op_hwp_fail", original="x", replacement="y",
                    operation="replace_text")
        result = render_hwp(b"hwp bytes", [c])

        self.assertEqual(result.applied_ids, [])
        self.assertEqual(result.output_bytes, b"")
        self.assertEqual(len(result.failed_items), 1)
        self.assertEqual(result.failed_items[0]["operation_id"], "op_hwp_fail")


# ── collect_applied_changes ──────────────────────────────────────────────────

from apps.documents.models import DocumentChange, DocumentVersion, FileStructure, UploadLog


def _make_user(username):
    return User.objects.create_user(username=username, password="pw")


def _make_upload(user, hash_val="collect_hash"):
    fs, _ = FileStructure.objects.get_or_create(
        hash=hash_val,
        defaults={"source_type": "excel", "column_schema": []},
    )
    return UploadLog.objects.create(
        user=user, file_structure=fs,
        original_filename="sample.xlsx",
        status=UploadLog.Status.DONE,
    )


def _make_version(upload, user):
    return DocumentVersion.objects.create(
        upload_log=upload, created_by=user,
        status=DocumentVersion.Status.DRAFT,
    )


def _make_change(version, operation_id, status, operation="replace_cell"):
    return DocumentChange.objects.create(
        version=version,
        operation_id=operation_id,
        format="excel",
        operation=operation,
        original="x", replacement="y",
        confidence=0.9,
        anchor={},
        status=status,
    )


class CollectAppliedChangesTest(TestCase):
    """collect_applied_changes: DB 접근 함수 테스트."""

    def setUp(self):
        self.user = _make_user("collect_user")
        self.upload = _make_upload(self.user)
        self.version = _make_version(self.upload, self.user)

    def test_returns_only_applied_changes(self):
        """applied 2건, rejected 1건 → applied 2건만 반환."""
        c1 = _make_change(self.version, "op_1", DocumentChange.Status.APPLIED)
        c2 = _make_change(self.version, "op_2", DocumentChange.Status.APPLIED)
        _make_change(self.version, "op_3", DocumentChange.Status.REJECTED)

        result = collect_applied_changes(self.version)

        ids = {c.operation_id for c in result}
        self.assertEqual(ids, {"op_1", "op_2"})

    def test_operations_filter_restricts_operation_type(self):
        """operations=["replace_text"] 전달 시 replace_cell은 제외한다."""
        _make_change(self.version, "op_cell", DocumentChange.Status.APPLIED, operation="replace_cell")
        _make_change(self.version, "op_text", DocumentChange.Status.APPLIED, operation="replace_text")

        result = collect_applied_changes(self.version, operations=["replace_text"])

        ids = {c.operation_id for c in result}
        self.assertEqual(ids, {"op_text"})

    def test_none_operations_returns_all_applied(self):
        """operations=None → operation 타입 불문하고 applied 전부 반환."""
        _make_change(self.version, "op_cell", DocumentChange.Status.APPLIED, operation="replace_cell")
        _make_change(self.version, "op_text", DocumentChange.Status.APPLIED, operation="replace_text")

        result = collect_applied_changes(self.version, operations=None)

        self.assertEqual(len(result), 2)


# ── persist_patch_result ─────────────────────────────────────────────────────

@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class PersistPatchResultTest(TestCase):
    """persist_patch_result: DB + storage 갱신 테스트."""

    def setUp(self):
        self.user = _make_user("persist_user")
        self.upload = _make_upload(self.user, "persist_hash")
        self.version = _make_version(self.upload, self.user)
        self.change = _make_change(self.version, "op_persist", DocumentChange.Status.APPLIED)

    def test_applied_ids_present_saves_artifact_and_marks_ready(self):
        """applied_ids가 있을 때 artifact_file이 저장되고 version.status=ready로 갱신된다."""
        result = PatchResult(
            output_bytes=b"fake xlsx bytes",
            applied_ids=["op_persist"],
            failed_items=[],
        )

        persist_patch_result(self.version, result, "xlsx", [self.change])

        self.version.refresh_from_db()
        self.assertEqual(self.version.status, DocumentVersion.Status.READY)
        self.assertEqual(self.version.applied_change_ids, ["op_persist"])
        self.assertTrue(bool(self.version.artifact_file), "artifact_file이 저장되어야 한다")
        self.assertTrue(default_storage.exists(self.version.artifact_file.name))

    def test_empty_applied_ids_sets_version_failed(self):
        """applied_ids=[] → version.status=failed, artifact_file 저장 안 됨."""
        result = PatchResult(
            output_bytes=b"",
            applied_ids=[],
            failed_items=[{"operation_id": "op_persist", "reason": "불일치"}],
        )

        persist_patch_result(self.version, result, "xlsx", [self.change])

        self.version.refresh_from_db()
        self.assertEqual(self.version.status, DocumentVersion.Status.FAILED)
        self.assertFalse(bool(self.version.artifact_file), "실패 시 artifact_file은 저장되지 않아야 한다")

    def test_failed_items_update_change_status(self):
        """failed_items의 operation_id에 해당하는 DocumentChange.status가 FAILED로 갱신된다."""
        result = PatchResult(
            output_bytes=b"",
            applied_ids=[],
            failed_items=[{"operation_id": "op_persist", "reason": "원본 불일치"}],
        )

        persist_patch_result(self.version, result, "xlsx", [self.change])

        self.change.refresh_from_db()
        self.assertEqual(self.change.status, DocumentChange.Status.FAILED)
