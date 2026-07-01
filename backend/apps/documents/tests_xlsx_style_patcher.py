"""
XLSX set_cell_style patcher 테스트 (document-format-editing-ax-v1-ko.md 11.1절 기준).

커버 범위:
  render_xlsx 단위 (1-12): validate_xlsx_style_change / apply_xlsx_cell_style 동작
  patch_document_version 통합 (13-15): replace_cell과 함께 적용, 전체/부분 실패
"""
import io

import openpyxl
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings

from apps.documents.models import (
    DocumentChange,
    DocumentVersion,
    FileStructure,
    UploadLog,
)
from apps.documents.patcher import (
    apply_xlsx_cell_style,
    collect_applied_changes,
    render_xlsx,
    validate_xlsx_style_change,
)
from apps.documents.tasks import patch_document_version

User = get_user_model()


# ── 픽스처 헬퍼 ───────────────────────────────────────────────────────────────


def _make_user(username):
    return User.objects.create_user(username=username, password="pw")


def _make_file_structure(hash_val):
    fs, _ = FileStructure.objects.get_or_create(
        hash=hash_val,
        defaults={"source_type": FileStructure.SourceType.EXCEL, "column_schema": []},
    )
    return fs


def _make_upload(user, fs):
    return UploadLog.objects.create(
        user=user,
        file_structure=fs,
        original_filename="header.xlsx",
    )


def _make_xlsx_bytes(sheet_name="Sheet1", data=None):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name
    if data:
        for cell_ref, value in data.items():
            ws[cell_ref] = value
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _header_xlsx_bytes():
    """A1:D1에 헤더("항목"~"금액")가 있는 4열 표본."""
    return _make_xlsx_bytes(
        sheet_name="Sheet1",
        data={"A1": "항목", "B1": "수량", "C1": "단가", "D1": "금액"},
    )


class _FakeChange:
    """DocumentChange ORM 없이 render_xlsx/validate 단위 테스트용 스텁."""

    def __init__(self, operation_id, anchor, patch, operation="set_cell_style"):
        self.operation_id = operation_id
        self.operation = operation
        self.anchor = anchor
        self.patch = patch
        self.original = ""
        self.replacement = ""


# _style_change(expected_context=...) 기본값 센티널 — None과 "생략"을 구분하기 위함
_DEFAULT_EXPECTED_CONTEXT = object()


def _style_change(
    operation_id="op_style",
    range_ref="A1:D1",
    patch=None,
    sheet="Sheet1",
    expected_context=_DEFAULT_EXPECTED_CONTEXT,
):
    """
    expected_context를 명시하지 않으면 표준(헤더 4셀) 컨텍스트를 채운다.
    expected_context=None을 넘기면 patch에서 expected_context 키 자체를 생략한다
    (필수 검증 테스트용). dict를 넘기면 그대로 사용한다(빈 dict, 잘못된 ref 등).
    """
    if expected_context is _DEFAULT_EXPECTED_CONTEXT:
        expected_context = {
            "sample_values": {"A1": "항목", "D1": "금액"},
            "non_empty_cells": ["A1", "B1", "C1", "D1"],
        }
    full_patch = dict(patch or {"font_bold": True})
    if expected_context is not None:
        full_patch["expected_context"] = expected_context
    return _FakeChange(
        operation_id,
        anchor={"type": "cell_range", "sheet": sheet, "range": range_ref},
        patch=full_patch,
    )


# ── render_xlsx 단위 테스트 (1-12) ────────────────────────────────────────────


class XlsxStyleRenderTest(TestCase):
    """render_xlsx의 set_cell_style 분기 단위 테스트."""

    def setUp(self):
        self.original_bytes = _header_xlsx_bytes()

    def _render(self, change):
        return render_xlsx(self.original_bytes, [change])

    def _load_result(self, result):
        self.assertEqual(result.failed_items, [], f"실패 없이 적용되어야 함: {result.failed_items}")
        return openpyxl.load_workbook(io.BytesIO(result.output_bytes), data_only=False)

    # 1. 성공 — bold 적용
    def test_bold_applied(self):
        change = _style_change(patch={"font_bold": True})
        result = self._render(change)
        wb = self._load_result(result)
        self.assertTrue(wb["Sheet1"]["A1"].font.bold, "A1 폰트가 굵게 적용되어야 한다")
        self.assertTrue(wb["Sheet1"]["D1"].font.bold, "D1 폰트가 굵게 적용되어야 한다")
        self.assertIn("op_style", result.applied_ids)

    # 2. fill_color 적용 — ARGB FF prefix 변환 확인
    def test_fill_color_applied_with_argb_ff_prefix(self):
        change = _style_change(patch={"fill_color": "D9EAF7"})
        result = self._render(change)
        wb = self._load_result(result)
        self.assertEqual(
            wb["Sheet1"]["A1"].fill.fgColor.rgb, "FFD9EAF7",
            "fill_color는 FF ARGB prefix가 붙어야 alpha가 보존된다",
        )

    # 3. horizontal/vertical alignment 적용
    def test_alignment_applied(self):
        change = _style_change(patch={"horizontal_alignment": "center", "vertical_alignment": "center"})
        result = self._render(change)
        wb = self._load_result(result)
        cell = wb["Sheet1"]["B1"]
        self.assertEqual(cell.alignment.horizontal, "center")
        self.assertEqual(cell.alignment.vertical, "center")

    # 4. border 적용
    def test_border_applied(self):
        change = _style_change(patch={"border": "thin"})
        result = self._render(change)
        wb = self._load_result(result)
        cell = wb["Sheet1"]["C1"]
        self.assertEqual(cell.border.left.style, "thin")
        self.assertEqual(cell.border.top.style, "thin")

    # 5. sheet 없음 → failed
    def test_missing_sheet_fails(self):
        change = _style_change(sheet="없는시트")
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertEqual(len(result.failed_items), 1)
        self.assertIn("시트 없음", result.failed_items[0]["reason"])

    # 6. range 문법 오류 → failed
    def test_invalid_range_syntax_fails(self):
        change = _style_change(range_ref="이상한범위!!")
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("range 문법 오류", result.failed_items[0]["reason"])

    # 7. range가 200셀 초과 → failed
    def test_oversized_range_fails(self):
        change = _style_change(range_ref="A1:J21")  # 10 * 21 = 210 > 200
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("range가 너무 큼", result.failed_items[0]["reason"])

    # 7-1. Excel 최대 열(XFD)을 벗어난 range → failed
    def test_out_of_bounds_range_fails(self):
        change = _style_change(
            range_ref="XFE1:XFE1",
            expected_context={"sample_values": {"XFE1": ""}, "non_empty_cells": ["XFE1"]},
        )
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("XLSX 허용 범위를 벗어남", result.failed_items[0]["reason"])

    # 8. sample_values 불일치 → failed
    def test_sample_value_mismatch_fails(self):
        change = _style_change()
        change.patch["expected_context"]["sample_values"]["A1"] = "다른값"
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("sample_value 불일치", result.failed_items[0]["reason"])

    # 9. non_empty_cells 중 빈 셀 → failed (range 안에 있지만 실제로 비어 있는 셀)
    def test_non_empty_cells_blank_fails(self):
        # range를 A1:D2로 넓혀 D2(2행, 헤더 데이터 없음)를 range 내부의 빈 셀로 사용한다.
        # range 밖 셀을 쓰면 "range 밖" 검증에 먼저 걸리므로 in-range 빈 셀이어야 한다.
        change = _style_change(range_ref="A1:D2")
        change.patch["expected_context"]["non_empty_cells"] = ["A1", "D2"]
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("필수 셀이 비어 있음", result.failed_items[0]["reason"])
        self.assertIn("D2", result.failed_items[0]["reason"])

    # 10. invalid fill_color → failed
    def test_invalid_fill_color_fails(self):
        change = _style_change(patch={"fill_color": "#ZZZZZZ"})
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("fill_color", result.failed_items[0]["reason"])

    # 11. invalid alignment → failed
    def test_invalid_alignment_fails(self):
        change = _style_change(patch={"horizontal_alignment": "justify"})
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("horizontal_alignment", result.failed_items[0]["reason"])

    # 12. invalid border → failed
    def test_invalid_border_fails(self):
        change = _style_change(patch={"border": "double"})
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("border", result.failed_items[0]["reason"])

    # 13. expected_context 자체가 없음(키 누락) → failed (검증 없이는 절대 적용 안 됨)
    def test_missing_expected_context_fails(self):
        change = _style_change(expected_context=None)
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("expected_context가 필요합니다", result.failed_items[0]["reason"])

    # 14. expected_context가 빈 dict → failed
    def test_empty_expected_context_fails(self):
        change = _style_change(expected_context={})
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("expected_context가 필요합니다", result.failed_items[0]["reason"])

    # 15. sample_values는 있지만 non_empty_cells가 없음 → failed
    def test_expected_context_missing_non_empty_cells_fails(self):
        change = _style_change(expected_context={"sample_values": {"A1": "항목"}})
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("sample_values와 non_empty_cells가 모두 필요", result.failed_items[0]["reason"])

    # 16. non_empty_cells는 있지만 sample_values가 빈 dict → failed
    def test_expected_context_empty_sample_values_fails(self):
        change = _style_change(expected_context={"sample_values": {}, "non_empty_cells": ["A1"]})
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("sample_values와 non_empty_cells가 모두 필요", result.failed_items[0]["reason"])

    # 17. sample_values의 셀 참조가 단일 셀이 아닌 range 문법 → failed (예외 아님)
    def test_invalid_context_ref_range_syntax_fails(self):
        change = _style_change(expected_context={
            "sample_values": {"A1:B1": "항목"},
            "non_empty_cells": ["A1"],
        })
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("expected_context 셀 참조 오류", result.failed_items[0]["reason"])

    # 18. non_empty_cells의 셀 참조가 완전히 깨진 문자열 → failed (예외 아님)
    def test_invalid_context_ref_garbage_fails(self):
        change = _style_change(expected_context={
            "sample_values": {"A1": "항목"},
            "non_empty_cells": ["A1", "이상한참조!!"],
        })
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("expected_context 셀 참조 오류", result.failed_items[0]["reason"])

    # 19. sample_values 셀 참조가 anchor.range 밖 → failed (값은 일치해도 위치가 다르면 거부)
    def test_context_ref_outside_range_fails(self):
        # E1은 range A1:D1 밖이다. 실제 워크북에 E1 값이 없어도 "range 밖" 사유로 실패해야 한다.
        change = _style_change(expected_context={
            "sample_values": {"A1": "항목", "E1": "범위밖"},
            "non_empty_cells": ["A1"],
        })
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("anchor.range 밖에 있음", result.failed_items[0]["reason"])
        self.assertIn("E1", result.failed_items[0]["reason"])

    # 20. non_empty_cells 셀 참조가 anchor.range 밖 → failed
    def test_non_empty_cells_ref_outside_range_fails(self):
        change = _style_change(expected_context={
            "sample_values": {"A1": "항목"},
            "non_empty_cells": ["A1", "F1"],
        })
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("anchor.range 밖에 있음", result.failed_items[0]["reason"])
        self.assertIn("F1", result.failed_items[0]["reason"])

    # 추가: whitelist 외 임의 키 → failed (임의 openpyxl 속성명 주입 방지)
    def test_unknown_patch_key_fails(self):
        change = _style_change(patch={"font_bold": True, "font_color": "FF0000"})
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("허용되지 않은 patch 필드", result.failed_items[0]["reason"])

    # 추가: validate 함수 자체가 통과 시 None을 반환하는지
    def test_validate_returns_none_on_success(self):
        wb = openpyxl.load_workbook(io.BytesIO(self.original_bytes))
        change = _style_change()
        self.assertIsNone(validate_xlsx_style_change(wb, change))

    # 추가: 단일 셀("A1")도 range로 허용되는지 (range_boundaries가 A1:A1과 동일 처리)
    def test_single_cell_range_allowed(self):
        change = _style_change(range_ref="A1")
        change.patch["expected_context"] = {
            "sample_values": {"A1": "항목"},
            "non_empty_cells": ["A1"],
        }
        result = self._render(change)
        self.assertEqual(result.failed_items, [])
        self.assertIn("op_style", result.applied_ids)

    # 추가: apply_xlsx_cell_style이 기존 스타일(폰트명 등)을 보존하는지
    def test_apply_preserves_existing_font_name(self):
        wb = openpyxl.load_workbook(io.BytesIO(self.original_bytes))
        wb["Sheet1"]["A1"].font = openpyxl.styles.Font(name="맑은 고딕", size=12)
        change = _style_change(patch={"font_bold": True})
        apply_xlsx_cell_style(wb, change)
        cell = wb["Sheet1"]["A1"]
        self.assertTrue(cell.font.bold)
        self.assertEqual(cell.font.name, "맑은 고딕", "기존 폰트명은 보존되어야 한다")


# ── patch_document_version 통합 테스트 (13-15) ────────────────────────────────


@override_settings(MEDIA_ROOT="/tmp/office_ax_xlsx_style_test")
class XlsxStylePatchTaskTest(TestCase):
    """replace_cell과 set_cell_style이 한 파일에서 함께 적용되는지, 실패 처리 검증."""

    def setUp(self):
        self.user = _make_user("style_patch_user")
        self.upload = _make_upload(self.user, _make_file_structure("style_patch_hash"))
        xlsx_bytes = _header_xlsx_bytes()
        self.upload.file.save("header.xlsx", ContentFile(xlsx_bytes), save=True)

        self.version = DocumentVersion.objects.create(
            upload_log=self.upload,
            created_by=self.user,
            status=DocumentVersion.Status.DRAFT,
        )

    def tearDown(self):
        try:
            if self.upload.file:
                self.upload.file.delete(save=False)
        except Exception:
            pass

    def _make_style_change(self, operation_id, **patch_overrides):
        expected_context = {
            "sample_values": {"A1": "항목", "D1": "금액"},
            "non_empty_cells": ["A1", "B1", "C1", "D1"],
        }
        patch = {"font_bold": True, **patch_overrides, "expected_context": expected_context}
        return DocumentChange.objects.create(
            version=self.version,
            operation_id=operation_id,
            format="excel",
            operation="set_cell_style",
            original="",
            replacement="",
            reason="헤더 정리",
            confidence=0.9,
            anchor={"type": "cell_range", "sheet": "Sheet1", "range": "A1:D1"},
            patch=patch,
            status=DocumentChange.Status.APPLIED,
        )

    # 13. replace_cell과 set_cell_style이 같은 파일에서 함께 적용된다
    def test_replace_cell_and_style_applied_together(self):
        DocumentChange.objects.create(
            version=self.version,
            operation_id="op_replace",
            format="excel",
            operation="replace_cell",
            original="항목",
            replacement="품목",
            reason="명칭 통일",
            confidence=0.9,
            anchor={"type": "cell", "sheet": "Sheet1", "cell": "A1"},
            status=DocumentChange.Status.APPLIED,
        )
        # replace_cell이 A1 텍스트를 바꾸므로, render_xlsx 내부 처리 순서에 의존하지 않도록
        # set_cell_style의 sample_values는 replace_cell이 건드리지 않는 D1만 검사한다.
        style_change = self._make_style_change("op_style")
        style_change.patch["expected_context"]["sample_values"] = {"D1": "금액"}
        style_change.save()

        operations = ["replace_cell", "set_cell_style"]
        changes = collect_applied_changes(self.version, operations=operations)
        with self.upload.file.open("rb") as f:
            original_bytes = f.read()
        result = render_xlsx(original_bytes, changes)

        self.assertEqual(result.failed_items, [], f"둘 다 성공해야 함: {result.failed_items}")
        wb = openpyxl.load_workbook(io.BytesIO(result.output_bytes))
        ws = wb["Sheet1"]
        self.assertEqual(str(ws["A1"].value), "품목", "replace_cell이 적용되어야 한다")
        self.assertTrue(ws["A1"].font.bold, "set_cell_style도 함께 적용되어야 한다")

    # 14. 모든 change가 실패하면 version이 failed 된다
    def test_all_style_changes_fail_sets_version_failed(self):
        self._make_style_change("op_style_bad", fill_color="ZZZZZZ")

        patch_document_version(self.version.pk)

        self.version.refresh_from_db()
        self.assertEqual(self.version.status, "failed")

    # 15. 일부 성공/일부 실패 — version은 ready, 실패 change는 failed
    def test_partial_success_sets_ready_and_failed_change(self):
        ok_change = self._make_style_change("op_style_ok")
        bad_change = self._make_style_change("op_style_bad", border="double")

        patch_document_version(self.version.pk)

        ok_change.refresh_from_db()
        bad_change.refresh_from_db()
        self.version.refresh_from_db()

        self.assertEqual(ok_change.status, "applied")
        self.assertEqual(bad_change.status, "failed")
        self.assertEqual(self.version.status, "ready")
