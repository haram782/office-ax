"""
XLSX set_number_format / set_formula patcher 테스트
(document-editing-ax-next-roadmap-v1-ko.md Phase 2-3절 기준).

커버 범위:
  render_xlsx 단위: validate_xlsx_number_format_change / apply_xlsx_number_format
                     validate_xlsx_formula_change / apply_xlsx_formula
  patch_document_version 통합: replace_cell + set_cell_style + set_number_format +
                                set_formula가 한 파일에서 함께 적용/부분 실패
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
    apply_xlsx_formula,
    apply_xlsx_number_format,
    collect_applied_changes,
    render_xlsx,
    validate_xlsx_formula_change,
    validate_xlsx_number_format_change,
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


def _make_upload(user, fs, filename="sales.xlsx"):
    return UploadLog.objects.create(
        user=user,
        file_structure=fs,
        original_filename=filename,
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


def _sales_xlsx_bytes():
    """
    A1:D1 헤더 + A2:D2 데이터 1행 + D5(합계 대상, 비어 있음)를 가진 표본.
    """
    return _make_xlsx_bytes(
        sheet_name="Sheet1",
        data={
            "A1": "항목", "B1": "수량", "C1": "단가", "D1": "금액",
            "A2": "사무용품", "B2": 10, "C2": 1000, "D2": 10000,
        },
    )


class _FakeChange:
    """DocumentChange ORM 없이 render_xlsx/validate 단위 테스트용 스텁."""

    def __init__(self, operation_id, anchor, patch, operation):
        self.operation_id = operation_id
        self.operation = operation
        self.anchor = anchor
        self.patch = patch
        self.original = ""
        self.replacement = ""


_DEFAULT = object()


def _format_change(
    operation_id="op_fmt",
    range_ref="D2:D2",
    number_format="#,##0원",
    sheet="Sheet1",
    expected_context=_DEFAULT,
):
    if expected_context is _DEFAULT:
        expected_context = {
            "sample_values": {"D2": "10000"},
            "non_empty_cells": ["D2"],
        }
    patch = {}
    if number_format is not _DEFAULT and number_format is not None:
        patch["number_format"] = number_format
    if expected_context is not None:
        patch["expected_context"] = expected_context
    return _FakeChange(
        operation_id,
        anchor={"type": "cell_range", "sheet": sheet, "range": range_ref},
        patch=patch,
        operation="set_number_format",
    )


def _formula_change(
    operation_id="op_formula",
    cell="D5",
    formula="=SUM(D2:D2)",
    sheet="Sheet1",
    anchor_type="cell",
    expected_context=_DEFAULT,
):
    if expected_context is _DEFAULT:
        expected_context = {
            "sample_values": {"D2": "10000"},
            "non_empty_cells": ["D2"],
        }
    patch = {}
    if formula is not _DEFAULT and formula is not None:
        patch["formula"] = formula
    if expected_context is not None:
        patch["expected_context"] = expected_context
    anchor = {"type": anchor_type, "sheet": sheet}
    if anchor_type == "cell":
        anchor["cell"] = cell
    else:
        anchor["range"] = cell
    return _FakeChange(operation_id, anchor=anchor, patch=patch, operation="set_formula")


# ── set_number_format 단위 테스트 ───────────────────────────────────────────


class XlsxNumberFormatRenderTest(TestCase):
    def setUp(self):
        self.original_bytes = _sales_xlsx_bytes()

    def _render(self, change):
        return render_xlsx(self.original_bytes, [change])

    # 1. 성공 — 허용된 number_format이 적용되고 값은 그대로 유지된다
    def test_number_format_applied_value_unchanged(self):
        change = _format_change(number_format="#,##0원")
        result = self._render(change)
        self.assertEqual(result.failed_items, [])
        wb = openpyxl.load_workbook(io.BytesIO(result.output_bytes))
        cell = wb["Sheet1"]["D2"]
        self.assertEqual(cell.number_format, "#,##0원")
        self.assertEqual(cell.value, 10000, "number_format 변경은 셀 값을 손상시키지 않아야 한다")
        self.assertIn("op_fmt", result.applied_ids)

    # 2. 성공 — 날짜 형식
    def test_date_format_applied(self):
        change = _format_change(
            range_ref="A2:A2",
            number_format="yyyy-mm-dd",
            expected_context={"sample_values": {"A2": "사무용품"}, "non_empty_cells": ["A2"]},
        )
        result = self._render(change)
        self.assertEqual(result.failed_items, [])
        wb = openpyxl.load_workbook(io.BytesIO(result.output_bytes))
        self.assertEqual(wb["Sheet1"]["A2"].number_format, "yyyy-mm-dd")

    # 3. expected_context 누락 → failed
    def test_missing_expected_context_fails(self):
        change = _format_change(expected_context=None)
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("expected_context가 필요합니다", result.failed_items[0]["reason"])

    # 4. range 문법 오류 → failed
    def test_invalid_range_fails(self):
        change = _format_change(range_ref="이상함!!")
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("range 문법 오류", result.failed_items[0]["reason"])

    # 5. range 200셀 초과 → failed
    def test_oversized_range_fails(self):
        change = _format_change(range_ref="A1:J21")
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("range가 너무 큼", result.failed_items[0]["reason"])

    # 5-1. Excel 최대 열(XFD)을 벗어난 range → failed
    def test_out_of_bounds_range_fails(self):
        change = _format_change(
            range_ref="XFE1:XFE1",
            expected_context={"sample_values": {"XFE1": ""}, "non_empty_cells": ["XFE1"]},
        )
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("XLSX 허용 범위를 벗어남", result.failed_items[0]["reason"])

    # 6. sample_value 불일치 → failed
    def test_sample_value_mismatch_fails(self):
        change = _format_change()
        change.patch["expected_context"]["sample_values"]["D2"] = "다른값"
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("sample_value 불일치", result.failed_items[0]["reason"])

    # 7. non_empty_cells 중 빈 셀 → failed
    def test_non_empty_cell_blank_fails(self):
        change = _format_change(
            range_ref="D2:D3",
            expected_context={"sample_values": {"D2": "10000"}, "non_empty_cells": ["D2", "D3"]},
        )
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("필수 셀이 비어 있음", result.failed_items[0]["reason"])
        self.assertIn("D3", result.failed_items[0]["reason"])

    # 8. 허용되지 않은 number_format → failed
    def test_unlisted_number_format_fails(self):
        change = _format_change(number_format="0.000")
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("허용되지 않은 number_format", result.failed_items[0]["reason"])

    # 9. number_format 누락 → failed
    def test_missing_number_format_fails(self):
        change = _format_change(number_format=None)
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("number_format이 필요합니다", result.failed_items[0]["reason"])

    # 10. 허용되지 않은 patch 키 → failed
    def test_unknown_patch_key_fails(self):
        change = _format_change()
        change.patch["font_bold"] = True
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("허용되지 않은 patch 필드", result.failed_items[0]["reason"])

    # 11. 시트 없음 → failed
    def test_missing_sheet_fails(self):
        change = _format_change(sheet="없는시트")
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("시트 없음", result.failed_items[0]["reason"])

    # 12. validate 함수가 성공 시 None 반환
    def test_validate_returns_none_on_success(self):
        wb = openpyxl.load_workbook(io.BytesIO(self.original_bytes))
        change = _format_change()
        self.assertIsNone(validate_xlsx_number_format_change(wb, change))

    # 13. apply 함수 단독 호출 시 number_format만 바뀐다
    def test_apply_sets_number_format_only(self):
        wb = openpyxl.load_workbook(io.BytesIO(self.original_bytes))
        change = _format_change(number_format="0.0%")
        apply_xlsx_number_format(wb, change)
        cell = wb["Sheet1"]["D2"]
        self.assertEqual(cell.number_format, "0.0%")
        self.assertEqual(cell.value, 10000)


# ── set_formula 단위 테스트 ─────────────────────────────────────────────────


class XlsxFormulaRenderTest(TestCase):
    def setUp(self):
        self.original_bytes = _sales_xlsx_bytes()

    def _render(self, change):
        return render_xlsx(self.original_bytes, [change])

    # 1. 성공 — SUM이 대상 셀에 저장된다
    def test_sum_formula_applied(self):
        change = _formula_change(formula="=SUM(D2:D2)")
        result = self._render(change)
        self.assertEqual(result.failed_items, [])
        wb = openpyxl.load_workbook(io.BytesIO(result.output_bytes), data_only=False)
        self.assertEqual(wb["Sheet1"]["D5"].value, "=SUM(D2:D2)")
        self.assertIn("op_formula", result.applied_ids)

    # 2. 성공 — 등호 없이 넘어와도 자동으로 붙는다
    def test_formula_without_leading_equals_is_normalized(self):
        change = _formula_change(formula="AVERAGE(D2:D2)")
        result = self._render(change)
        self.assertEqual(result.failed_items, [])
        wb = openpyxl.load_workbook(io.BytesIO(result.output_bytes), data_only=False)
        self.assertEqual(wb["Sheet1"]["D5"].value, "=AVERAGE(D2:D2)")

    # 3. 성공 — 중첩 함수(IF 안의 SUM)
    def test_nested_function_allowed(self):
        change = _formula_change(formula="=IF(COUNT(D2:D2)>0,SUM(D2:D2),0)")
        result = self._render(change)
        self.assertEqual(result.failed_items, [], f"중첩 허용 함수는 통과해야 함: {result.failed_items}")
        wb = openpyxl.load_workbook(io.BytesIO(result.output_bytes), data_only=False)
        self.assertEqual(wb["Sheet1"]["D5"].value, "=IF(COUNT(D2:D2)>0,SUM(D2:D2),0)")

    # 3-1. 성공 — 허용 함수 결과에 산술 연산자를 붙이는 형태
    def test_function_result_arithmetic_allowed(self):
        change = _formula_change(formula="=SUM(D2:D2)*2")
        result = self._render(change)
        self.assertEqual(result.failed_items, [], f"함수 결과 산술 연산은 통과해야 함: {result.failed_items}")
        wb = openpyxl.load_workbook(io.BytesIO(result.output_bytes), data_only=False)
        self.assertEqual(wb["Sheet1"]["D5"].value, "=SUM(D2:D2)*2")

    # 3-2. 성공 — 함수 안의 다중 range 인자
    def test_multi_range_arguments_allowed(self):
        change = _formula_change(formula="=SUM(D2:D2,C2:C2)")
        result = self._render(change)
        self.assertEqual(result.failed_items, [], f"다중 range 인자는 통과해야 함: {result.failed_items}")
        wb = openpyxl.load_workbook(io.BytesIO(result.output_bytes), data_only=False)
        self.assertEqual(wb["Sheet1"]["D5"].value, "=SUM(D2:D2,C2:C2)")

    # 4. range 대상 거부 (1차 범위는 단일 셀만)
    def test_range_target_rejected(self):
        change = _formula_change(anchor_type="cell_range", cell="D5:D6")
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("단일 셀", result.failed_items[0]["reason"])

    # 5. expected_context 누락 → failed
    def test_missing_expected_context_fails(self):
        change = _formula_change(expected_context=None)
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("expected_context가 필요합니다", result.failed_items[0]["reason"])

    # 6. 외부 시트 참조("!") → failed
    def test_external_sheet_ref_rejected(self):
        change = _formula_change(formula="=SUM(Sheet2!A1:A2)")
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("금지된 패턴", result.failed_items[0]["reason"])

    # 7. 외부 통합문서 참조("[...]") → failed
    def test_external_workbook_ref_rejected(self):
        change = _formula_change(formula="=SUM([Book1.xlsx]Sheet1!A1)")
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("금지된 패턴", result.failed_items[0]["reason"])

    # 8. URL → failed
    def test_url_rejected(self):
        change = _formula_change(formula='=HYPERLINK("https://evil.example.com","x")')
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("금지된 패턴", result.failed_items[0]["reason"])

    # 9. 금지 함수 INDIRECT → failed
    def test_forbidden_function_indirect_rejected(self):
        change = _formula_change(formula="=INDIRECT(D2)")
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("금지된 함수", result.failed_items[0]["reason"])

    # 10. 금지 함수 WEBSERVICE → failed
    def test_forbidden_function_webservice_rejected(self):
        change = _formula_change(formula='=WEBSERVICE("x")')
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("금지된", result.failed_items[0]["reason"])

    # 11. 알 수 없는 함수 → failed
    def test_unknown_function_rejected(self):
        change = _formula_change(formula="=FOOBAR(D2:D2)")
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("알 수 없거나 허용되지 않은 함수", result.failed_items[0]["reason"])

    # 12. 괄호 불일치(malformed) → failed
    def test_malformed_formula_unbalanced_parens_rejected(self):
        change = _formula_change(formula="=SUM(D2:D2")
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("괄호가 일치하지 않음", result.failed_items[0]["reason"])

    # 13. 빈 formula → failed
    def test_empty_formula_rejected(self):
        change = _formula_change(formula="")
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("비어 있지 않은 문자열", result.failed_items[0]["reason"])

    # 14. 함수 호출이 전혀 없는 순수 산술식 → failed (whitelist 함수 강제)
    def test_bare_arithmetic_without_function_rejected(self):
        change = _formula_change(formula="=D2+D2")
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("허용된 함수 호출을 포함해야 함", result.failed_items[0]["reason"])

    # 15. 매크로/문자열 연결("&") → failed
    def test_string_concat_rejected(self):
        change = _formula_change(formula='=SUM(D2:D2)&"원"')
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("금지된 패턴", result.failed_items[0]["reason"])

    # 15-1. 함수 호출 뒤에 셀 참조가 붙는 trailing token → failed
    def test_trailing_cell_reference_rejected(self):
        change = _formula_change(formula="=SUM(D2:D2) B2")
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("연산자 또는 구분자가 필요함", result.failed_items[0]["reason"])

    # 15-2. 공백 없는 trailing token도 rejected
    def test_adjacent_trailing_cell_reference_rejected(self):
        change = _formula_change(formula="=SUM(D2:D2)B2")
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("연산자 또는 구분자가 필요함", result.failed_items[0]["reason"])

    # 15-3. 최상위 함수 뒤 comma와 셀 참조가 붙는 trailing token → failed
    def test_top_level_comma_trailing_cell_reference_rejected(self):
        change = _formula_change(formula="=SUM(D2:D2), B2")
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("인자 구분자는 함수 내부", result.failed_items[0]["reason"])

    # 15-4. Excel 공백 교차 참조 형태 → failed
    def test_space_intersection_reference_rejected(self):
        change = _formula_change(formula="=SUM(D2 D2)")
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("연산자 또는 구분자가 필요함", result.failed_items[0]["reason"])

    # 16. 허용되지 않은 patch 키 → failed
    def test_unknown_patch_key_fails(self):
        change = _formula_change()
        change.patch["number_format"] = "#,##0"
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("허용되지 않은 patch 필드", result.failed_items[0]["reason"])

    # 17. 시트 없음 → failed
    def test_missing_sheet_fails(self):
        change = _formula_change(sheet="없는시트")
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("시트 없음", result.failed_items[0]["reason"])

    # 18. anchor.cell 문법 오류 → failed
    def test_invalid_cell_ref_fails(self):
        change = _formula_change(cell="이상함!!")
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("anchor.cell 문법 오류", result.failed_items[0]["reason"])

    # 18-1. Excel 최대 열(XFD)을 벗어난 대상 셀 → failed
    def test_out_of_bounds_target_cell_fails(self):
        change = _formula_change(cell="XFE1")
        result = self._render(change)
        self.assertEqual(result.applied_ids, [])
        self.assertIn("XLSX 허용 범위를 벗어남", result.failed_items[0]["reason"])

    # 19. validate 함수 성공 시 None 반환
    def test_validate_returns_none_on_success(self):
        wb = openpyxl.load_workbook(io.BytesIO(self.original_bytes))
        change = _formula_change()
        self.assertIsNone(validate_xlsx_formula_change(wb, change))

    # 20. apply 함수 단독 호출
    def test_apply_sets_formula_string(self):
        wb = openpyxl.load_workbook(io.BytesIO(self.original_bytes))
        change = _formula_change(formula="=MAX(D2:D2)")
        apply_xlsx_formula(wb, change)
        self.assertEqual(wb["Sheet1"]["D5"].value, "=MAX(D2:D2)")


# ── patch_document_version 통합 테스트 ──────────────────────────────────────


@override_settings(MEDIA_ROOT="/tmp/office_ax_xlsx_format_formula_test")
class XlsxFormatFormulaPatchTaskTest(TestCase):
    """replace_cell + set_cell_style + set_number_format + set_formula 혼합 적용/부분 실패."""

    def setUp(self):
        self.user = _make_user("format_formula_patch_user")
        self.upload = _make_upload(self.user, _make_file_structure("format_formula_hash"))
        xlsx_bytes = _sales_xlsx_bytes()
        self.upload.file.save("sales.xlsx", ContentFile(xlsx_bytes), save=True)

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

    def _make_style_change(self, operation_id):
        return DocumentChange.objects.create(
            version=self.version,
            operation_id=operation_id,
            format="excel",
            operation="set_cell_style",
            original="",
            replacement="",
            reason="헤더 강조",
            confidence=0.9,
            anchor={"type": "cell_range", "sheet": "Sheet1", "range": "A1:D1"},
            patch={
                "font_bold": True,
                "expected_context": {
                    "sample_values": {"A1": "항목", "D1": "금액"},
                    "non_empty_cells": ["A1", "B1", "C1", "D1"],
                },
            },
            status=DocumentChange.Status.APPLIED,
        )

    def _make_format_change(self, operation_id, number_format="#,##0원"):
        return DocumentChange.objects.create(
            version=self.version,
            operation_id=operation_id,
            format="excel",
            operation="set_number_format",
            original="",
            replacement="",
            reason="금액 표시 형식 정리",
            confidence=0.9,
            anchor={"type": "cell_range", "sheet": "Sheet1", "range": "D2:D2"},
            patch={
                "number_format": number_format,
                "expected_context": {
                    "sample_values": {"D2": "10000"},
                    "non_empty_cells": ["D2"],
                },
            },
            status=DocumentChange.Status.APPLIED,
        )

    def _make_formula_change(self, operation_id, formula="=SUM(D2:D2)"):
        return DocumentChange.objects.create(
            version=self.version,
            operation_id=operation_id,
            format="excel",
            operation="set_formula",
            original="",
            replacement="",
            reason="합계 계산",
            confidence=0.9,
            anchor={"type": "cell", "sheet": "Sheet1", "cell": "D5"},
            patch={
                "formula": formula,
                "expected_context": {
                    "sample_values": {"D2": "10000"},
                    "non_empty_cells": ["D2"],
                },
            },
            status=DocumentChange.Status.APPLIED,
        )

    # 1. 네 operation이 한 파일에서 함께 적용된다
    def test_all_four_operations_applied_together(self):
        DocumentChange.objects.create(
            version=self.version,
            operation_id="op_replace",
            format="excel",
            operation="replace_cell",
            original="사무용품",
            replacement="사무 소모품",
            reason="명칭 통일",
            confidence=0.9,
            anchor={"type": "cell", "sheet": "Sheet1", "cell": "A2"},
            status=DocumentChange.Status.APPLIED,
        )
        self._make_style_change("op_style")
        self._make_format_change("op_format")
        self._make_formula_change("op_formula")

        operations = ["replace_cell", "set_cell_style", "set_number_format", "set_formula"]
        changes = collect_applied_changes(self.version, operations=operations)
        with self.upload.file.open("rb") as f:
            original_bytes = f.read()
        result = render_xlsx(original_bytes, changes)

        self.assertEqual(result.failed_items, [], f"넷 다 성공해야 함: {result.failed_items}")
        wb = openpyxl.load_workbook(io.BytesIO(result.output_bytes), data_only=False)
        ws = wb["Sheet1"]
        self.assertEqual(str(ws["A2"].value), "사무 소모품")
        self.assertTrue(ws["A1"].font.bold)
        self.assertEqual(ws["D2"].number_format, "#,##0원")
        self.assertEqual(ws["D5"].value, "=SUM(D2:D2)")

    # 2. patch_document_version을 통해 실행 — 태스크 레벨 operation 필터에 포함되는지 확인
    def test_patch_document_version_includes_new_operations(self):
        self._make_format_change("op_format_task")
        self._make_formula_change("op_formula_task")

        patch_document_version(self.version.pk)

        self.version.refresh_from_db()
        self.assertEqual(self.version.status, DocumentVersion.Status.READY)

        with self.version.artifact_file.open("rb") as f:
            wb = openpyxl.load_workbook(io.BytesIO(f.read()), data_only=False)
        ws = wb["Sheet1"]
        self.assertEqual(ws["D2"].number_format, "#,##0원")
        self.assertEqual(ws["D5"].value, "=SUM(D2:D2)")

    # 3. 일부 실패 — 나머지 성공 change는 유지되고 version은 ready
    def test_partial_failure_keeps_successful_changes(self):
        ok_change = self._make_format_change("op_format_ok")
        bad_change = self._make_format_change("op_format_bad", number_format="0.000")
        formula_ok = self._make_formula_change("op_formula_ok")
        formula_bad = self._make_formula_change("op_formula_bad", formula="=INDIRECT(D2)")

        patch_document_version(self.version.pk)

        ok_change.refresh_from_db()
        bad_change.refresh_from_db()
        formula_ok.refresh_from_db()
        formula_bad.refresh_from_db()
        self.version.refresh_from_db()

        self.assertEqual(ok_change.status, DocumentChange.Status.APPLIED)
        self.assertEqual(bad_change.status, DocumentChange.Status.FAILED)
        self.assertEqual(formula_ok.status, DocumentChange.Status.APPLIED)
        self.assertEqual(formula_bad.status, DocumentChange.Status.FAILED)
        self.assertEqual(self.version.status, DocumentVersion.Status.READY)
