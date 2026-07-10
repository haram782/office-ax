"""
문서 패치 순수화 모듈.

3단계 분리:
  collect_applied_changes  — DB에서 applied change 수집 (유일한 DB 읽기 지점)
  render_*                 — 순수 변환 함수: bytes in → PatchResult out, DB I/O 없음
  persist_patch_result     — 결과 영속화: DB + storage 갱신 (유일한 DB 쓰기 지점)

render_* 사용 규칙:
  - DocumentChange ORM 인스턴스를 인자로 받을 수 있다.
  - 단, 함수 안에서 .save() / .objects.filter() 등 DB 접근은 절대 하지 않는다.
  - 예외를 caller로 전파하지 않는다 — 실패는 PatchResult.failed_items로,
    "위치 후보가 여러 개라 자동 반영을 멈춘 경우"(render_pdf·render_docx)는
    needs_confirmation_items로 구분해 표현한다(anchor_resolution.py AnchorStatus 참고).
  - applied_ids가 비어있으면 output_bytes = b""로 설정한다.

PDF의 text_match anchor 해석은 이 모듈이 아니라 anchor_resolution.py의
AnchorResolver가 담당한다 — render_pdf는 그 결과(RESOLVED/AMBIGUOUS/NOT_FOUND/
UNSUPPORTED)를 렌더링 여부·실패 사유 분류에만 사용한다.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


# ── 실패 사유 코드 (document-edit-execution-layer-design-v1-ko.md 8절) ──────────

# "생성 실패"와 "위치 확인 필요"를 구분하는 UX를 위해 실패 사유를 안정된 코드로
# 고정한다. human-readable reason과 별개로 failed_items/needs_confirmation_items
# 원소의 "code" 키에 담는다. 전체 코드 표는 설계 문서 8절 참조 — 여기에는
# patcher가 직접 발급하는 코드만 둔다.
FAILURE_CODE_AMBIGUOUS_ANCHOR = "ambiguous_anchor"
FAILURE_CODE_RENDER_VALIDATION_FAILED = "render_validation_failed"


# ── set_cell_style 상수 (document-format-editing-ax-v1-ko.md 7절 기준) ───────────

# 1차 구현은 최대 200셀까지만 허용한다 (anchor.range 검증 시 사용).
# set_number_format도 동일한 range 크기 제한을 재사용한다 (roadmap v1 5.2절).
_STYLE_MAX_RANGE_CELLS = 200
_FORMAT_MAX_RANGE_CELLS = _STYLE_MAX_RANGE_CELLS

# patch에 허용된 키. expected_context는 DB 저장 시 patch에 병합되므로 함께 허용한다.
_STYLE_ALLOWED_PATCH_KEYS = {
    "font_bold",
    "fill_color",
    "horizontal_alignment",
    "vertical_alignment",
    "border",
    "expected_context",
}
_STYLE_HORIZONTAL_ALIGNMENTS = {"left", "center", "right"}
_STYLE_VERTICAL_ALIGNMENTS = {"top", "center", "bottom"}
_STYLE_BORDER_STYLES = {"thin", "medium", "none"}
_STYLE_FILL_COLOR_RE = re.compile(r"^[0-9A-Fa-f]{6}$")


# ── set_number_format 상수 (roadmap v1 6.Phase2절 기준) ─────────────────────────

_NUMBER_FORMAT_ALLOWED_PATCH_KEYS = {"number_format", "expected_context"}
_NUMBER_FORMAT_WHITELIST = {
    "yyyy-mm-dd",
    "yyyy. mm. dd",
    "#,##0",
    "#,##0원",
    "#,##0.00",
    "0.0%",
    "0.00%",
}


# ── set_formula 상수 (roadmap v1 6.Phase3절 기준) ───────────────────────────────

# Excel 워크시트의 실제 최대 열/행 (XFD1048576) — expected_context 셀 참조가
# "시트 범위 안의 그럴듯한 셀"인지 검증할 때 bounds로 사용한다.
_XLSX_MAX_COLUMNS = 16384
_XLSX_MAX_ROWS = 1048576

_FORMULA_ALLOWED_PATCH_KEYS = {"formula", "expected_context"}
_FORMULA_ALLOWED_FUNCTIONS = {"SUM", "AVERAGE", "COUNT", "COUNTA", "MIN", "MAX", "IF"}
# 알려진 위험 함수는 whitelist에 없어도 별도로 명시해 더 구체적인 실패 사유를 준다
# (외부 데이터 조회, 동적 참조, 임의 셀 실행 등 patch 검증을 우회할 수 있는 함수군).
_FORMULA_FORBIDDEN_FUNCTIONS = {
    "INDIRECT", "HYPERLINK", "WEBSERVICE", "IMPORTRANGE", "IMPORTDATA",
    "IMPORTXML", "FILTERXML", "RTD", "EXEC", "CALL", "REGISTER", "SHELL", "CELL",
}
# 함수 호출 형태(이름 뒤 괄호)를 찾는 정규식 — 중첩 호출(IF 안의 SUM 등)도 함께 잡는다.
_FORMULA_FUNCTION_CALL_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_.]*)\s*\(")
# 허용 문자 집합: 영숫자, 괄호, 콤마, 콜론(range), 사칙연산, 비교연산, 따옴표, 공백.
# '!'(시트 참조/외부 참조), '['/']'(외부 통합문서 참조), 'http/www'(URL), '&'(문자열 연결)는
# 의도적으로 제외해 외부 참조·매크로 진입 경로를 charset 단계에서부터 차단한다.
_FORMULA_CHARSET_RE = re.compile(r'^[A-Za-z0-9_()+\-*/:,.\s<>="]*$')
_FORMULA_FORBIDDEN_SUBSTRING_RE = re.compile(
    r"(https?://|www\.|\\\\|\[|\]|!|'|@|&)", re.IGNORECASE,
)
_FORMULA_CELL_REF_RE = re.compile(
    r"\$?[A-Za-z]{1,3}\$?[0-9]{1,7}(?::\$?[A-Za-z]{1,3}\$?[0-9]{1,7})?"
)
_FORMULA_LITERAL_RE = re.compile(r"TRUE|FALSE", re.IGNORECASE)


# ── 공용 결과 타입 ─────────────────────────────────────────────────────────────

@dataclass
class PatchResult:
    """render_* 함수의 반환 타입. DB I/O 없이 순수한 변환 결과만 담는다."""
    output_bytes: bytes
    applied_ids: list[str] = field(default_factory=list)
    failed_items: list[dict] = field(default_factory=list)
    # failed_items 원소 형식: {"operation_id": str, "reason": str}
    # (안정된 실패 사유 코드가 있는 경우 "code" 키를 추가로 담는다 — 설계 문서 8절)
    # 후보가 여러 개라 자동 반영을 멈춘 항목 (render_pdf의 AnchorResolver AMBIGUOUS,
    # render_docx의 text_match 다중 매치).
    # failed_items와 분리하는 이유: "위치를 못 찾음/지원 안 함"과 "후보가 여러 개라
    # 확인이 필요함"은 원인과 후속 조치(재시도 vs 사용자 확인)가 다르다.
    needs_confirmation_items: list[dict] = field(default_factory=list)


# ── 1단계: collect ─────────────────────────────────────────────────────────────

def collect_applied_changes(version, operations: list[str] | None = None) -> list:
    """
    DB에서 version에 속한 status=APPLIED DocumentChange를 수집한다.

    operations: ["replace_cell"] 처럼 operation 타입 필터를 줄 수 있다.
                None이면 모든 operation 타입을 포함한다.
    """
    from .models import DocumentChange

    qs = DocumentChange.objects.filter(
        version=version,
        status=DocumentChange.Status.APPLIED,
    )
    if operations is not None:
        qs = qs.filter(operation__in=operations)
    return list(qs)


# ── 2단계: render — 순수 변환 ─────────────────────────────────────────────────

def render_xlsx(original_bytes: bytes, changes: list) -> PatchResult:
    """
    XLSX bytes + applied change 목록 → PatchResult.

    replace_cell operation: anchor.sheet / anchor.cell 으로 셀을 특정하고
    original과 실제 값이 일치하면 replacement로 교체한다.
    불일치·시트 없음 → failed_items에 기록.

    set_cell_style operation: anchor.sheet / anchor.range(cell_range)로 영역을 특정하고
    expected_context 검증 통과 시 patch whitelist 필드만 적용한다.
    검증 실패 → failed_items에 기록 (document-format-editing-ax-v1-ko.md 7-8절 기준).

    set_number_format operation: set_cell_style과 동일한 anchor.range/expected_context
    구조를 사용하며 patch.number_format이 whitelist에 있어야 적용한다.

    set_formula operation: anchor.type=cell(단일 셀)만 허용하고, patch.formula가
    보수적 whitelist(SUM/AVERAGE/COUNT/COUNTA/MIN/MAX/IF)를 통과해야 적용한다.
    """
    import openpyxl

    try:
        wb = openpyxl.load_workbook(io.BytesIO(original_bytes), data_only=False)
    except Exception as exc:
        # 원본 파일 파싱 실패 — 모든 change를 failed로 처리
        return PatchResult(
            b"",
            [],
            [{"operation_id": c.operation_id, "reason": f"XLSX 로드 실패: {exc}"} for c in changes],
        )

    applied_ids: list[str] = []
    failed_items: list[dict] = []

    _RANGE_OPS = {
        "set_cell_style": (validate_xlsx_style_change, apply_xlsx_cell_style),
        "set_number_format": (validate_xlsx_number_format_change, apply_xlsx_number_format),
        "set_formula": (validate_xlsx_formula_change, apply_xlsx_formula),
    }

    for change in changes:
        op_pair = _RANGE_OPS.get(change.operation)
        if op_pair is not None:
            validate_fn, apply_fn = op_pair
            # validate/apply 내부에서 예상치 못한 예외(예: 잘못된 셀 참조 파싱)가 나더라도
            # caller로 전파하지 않고 failed_items로 변환한다 (모듈 상단 render_* 규칙).
            try:
                error = validate_fn(wb, change)
            except Exception as exc:
                error = f"검증 중 예외 발생: {exc}"
            if error is not None:
                failed_items.append({"operation_id": change.operation_id, "reason": error})
                logger.warning(
                    "render_xlsx: %s 검증 실패 | op=%s | reason=%s",
                    change.operation, change.operation_id, error,
                )
                continue
            try:
                apply_fn(wb, change)
            except Exception as exc:
                failed_items.append({
                    "operation_id": change.operation_id,
                    "reason": f"적용 중 예외 발생: {exc}",
                })
                logger.warning(
                    "render_xlsx: %s 적용 실패 | op=%s | exc=%s",
                    change.operation, change.operation_id, exc,
                )
                continue
            applied_ids.append(change.operation_id)
            continue

        sheet_name = change.anchor.get("sheet", "")
        cell_ref = change.anchor.get("cell", "")

        if sheet_name not in wb.sheetnames:
            failed_items.append({
                "operation_id": change.operation_id,
                "reason": f"시트 없음: {sheet_name}",
            })
            logger.warning("render_xlsx: 시트 없음 | sheet=%s | op=%s", sheet_name, change.operation_id)
            continue

        ws = wb[sheet_name]
        current_value = str(ws[cell_ref].value) if ws[cell_ref].value is not None else ""

        if current_value != change.original:
            failed_items.append({
                "operation_id": change.operation_id,
                "reason": f"원본 값 불일치: expected={change.original!r}, actual={current_value!r}",
            })
            logger.warning(
                "render_xlsx: 원본 값 불일치 | op=%s | expected=%r actual=%r",
                change.operation_id, change.original, current_value,
            )
            continue

        ws[cell_ref] = change.replacement
        applied_ids.append(change.operation_id)

    if not applied_ids:
        return PatchResult(b"", [], failed_items)

    output = io.BytesIO()
    wb.save(output)
    return PatchResult(output.getvalue(), applied_ids, failed_items)


def validate_xlsx_style_change(wb, change) -> str | None:
    """
    set_cell_style change를 검증한다. 통과 시 None, 실패 시 실패 사유 문자열을 반환한다.

    검증 순서: 시트 존재 → range 문법/크기 → patch whitelist → expected_context 존재·셀 참조 →
    sample_values/non_empty_cells 실값 대조.

    expected_context는 서식 변경이 엉뚱한 영역에 적용되는 것을 막는 유일한 안전장치이므로
    (document-format-editing-ax-v1-ko.md 3.3절) 누락·빈 값이면 무조건 실패시킨다.
    """
    sheet_name = change.anchor.get("sheet", "")
    range_ref = change.anchor.get("range", "")

    range_error, bounds = _validate_xlsx_range(wb, sheet_name, range_ref, _STYLE_MAX_RANGE_CELLS)
    if range_error is not None:
        return range_error
    min_col, min_row, max_col, max_row = bounds

    patch = change.patch or {}
    whitelist_error = _validate_xlsx_style_patch_whitelist(patch)
    if whitelist_error is not None:
        return whitelist_error

    return _validate_xlsx_range_expected_context(
        wb[sheet_name], patch.get("expected_context"), "set_cell_style", min_col, min_row, max_col, max_row,
    )


def _validate_xlsx_range(
    wb, sheet_name: str, range_ref: str, max_cells: int,
) -> tuple[str | None, tuple[int, int, int, int] | None]:
    """
    anchor.sheet / anchor.range 공통 검증. set_cell_style과 set_number_format이 공유한다.

    통과 시 (None, (min_col, min_row, max_col, max_row)), 실패 시 (사유 문자열, None).
    """
    from openpyxl.utils.cell import range_boundaries

    if sheet_name not in wb.sheetnames:
        return f"시트 없음: {sheet_name}", None

    try:
        min_col, min_row, max_col, max_row = range_boundaries(range_ref)
        if min_col is None or min_row is None or max_col is None or max_row is None:
            raise ValueError("range_boundaries가 None을 반환")
    except (ValueError, TypeError, AttributeError):
        return f"range 문법 오류: {range_ref!r}", None

    cell_count = (max_col - min_col + 1) * (max_row - min_row + 1)
    if cell_count > max_cells:
        return f"range가 너무 큼: {cell_count}셀 (최대 {max_cells}셀)", None
    if (
        min_col < 1 or max_col > _XLSX_MAX_COLUMNS
        or min_row < 1 or max_row > _XLSX_MAX_ROWS
    ):
        return f"range가 XLSX 허용 범위를 벗어남: {range_ref!r}", None

    return None, (min_col, min_row, max_col, max_row)


def _validate_xlsx_range_expected_context(
    ws, expected_context, op_label: str, min_col: int, min_row: int, max_col: int, max_row: int,
) -> str | None:
    """
    expected_context 존재·형식·셀 참조(anchor.range 내부)를 검증한 뒤 sample_values/
    non_empty_cells를 워크북 실값과 대조한다. set_cell_style과 set_number_format이 공유한다.
    """
    context_error = _validate_xlsx_range_expected_context_shape(
        expected_context, op_label, min_col, min_row, max_col, max_row,
    )
    if context_error is not None:
        return context_error

    sample_values = expected_context.get("sample_values")
    for cell_ref, expected_value in sample_values.items():
        actual = ws[cell_ref].value
        actual_str = str(actual) if actual is not None else ""
        if actual_str != str(expected_value):
            return f"sample_value 불일치: {cell_ref} expected={expected_value!r} actual={actual_str!r}"

    non_empty_cells = expected_context.get("non_empty_cells")
    for cell_ref in non_empty_cells:
        if ws[cell_ref].value in (None, ""):
            return f"필수 셀이 비어 있음: {cell_ref}"

    return None


def _validate_xlsx_range_expected_context_shape(
    expected_context, op_label: str, min_col: int, min_row: int, max_col: int, max_row: int,
) -> str | None:
    """
    expected_context 존재 여부와 형식, 그리고 모든 셀 참조가 유효한 A1 단일 셀이면서
    anchor.range 내부에 있는지 검증한다. op_label로 지정된 operation은 expected_context
    없이 적용할 수 없다.
    """
    if not isinstance(expected_context, dict) or not expected_context:
        return f"expected_context가 필요합니다 ({op_label}은 검증 없이 적용할 수 없음)"

    sample_values = expected_context.get("sample_values")
    non_empty_cells = expected_context.get("non_empty_cells")
    if not sample_values or not non_empty_cells:
        return "expected_context에는 sample_values와 non_empty_cells가 모두 필요합니다"

    if not isinstance(sample_values, dict):
        return f"sample_values는 객체여야 함: {sample_values!r}"
    if not isinstance(non_empty_cells, list):
        return f"non_empty_cells는 배열이어야 함: {non_empty_cells!r}"

    all_refs = list(sample_values.keys()) + list(non_empty_cells)
    for cell_ref in all_refs:
        ref_error = _validate_xlsx_context_cell_ref(cell_ref, min_col, min_row, max_col, max_row)
        if ref_error is not None:
            return ref_error

    return None


def _validate_xlsx_context_cell_ref(
    cell_ref, min_col: int, min_row: int, max_col: int, max_row: int,
) -> str | None:
    """단일 A1 셀 참조 문법인지, anchor.range 내부 좌표인지 검증한다."""
    from openpyxl.utils.cell import coordinate_to_tuple

    if not isinstance(cell_ref, str):
        return f"expected_context 셀 참조는 문자열이어야 함: {cell_ref!r}"

    try:
        row, col = coordinate_to_tuple(cell_ref)
    except (ValueError, TypeError, AttributeError, KeyError):
        return f"expected_context 셀 참조 오류: {cell_ref!r}"

    if not (min_row <= row <= max_row and min_col <= col <= max_col):
        return f"expected_context 셀이 anchor.range 밖에 있음: {cell_ref!r}"

    return None


def _validate_xlsx_style_patch_whitelist(patch: dict) -> str | None:
    """patch에 허용되지 않은 키나 값이 있으면 실패 사유를 반환한다."""
    unknown_keys = set(patch.keys()) - _STYLE_ALLOWED_PATCH_KEYS
    if unknown_keys:
        return f"허용되지 않은 patch 필드: {sorted(unknown_keys)}"

    font_bold = patch.get("font_bold")
    if font_bold is not None and not isinstance(font_bold, bool):
        return f"font_bold는 boolean이어야 함: {font_bold!r}"

    fill_color = patch.get("fill_color")
    if fill_color is not None:
        if not isinstance(fill_color, str) or not _STYLE_FILL_COLOR_RE.match(fill_color):
            return f"fill_color 형식 오류 (RRGGBB 6자리 필요): {fill_color!r}"

    h_align = patch.get("horizontal_alignment")
    if h_align is not None and h_align not in _STYLE_HORIZONTAL_ALIGNMENTS:
        return f"horizontal_alignment 허용값 아님: {h_align!r}"

    v_align = patch.get("vertical_alignment")
    if v_align is not None and v_align not in _STYLE_VERTICAL_ALIGNMENTS:
        return f"vertical_alignment 허용값 아님: {v_align!r}"

    border = patch.get("border")
    if border is not None and border not in _STYLE_BORDER_STYLES:
        return f"border 허용값 아님: {border!r}"

    return None


def apply_xlsx_cell_style(wb, change) -> None:
    """
    검증을 통과한 set_cell_style change를 워크북에 적용한다.

    기존 스타일 객체는 immutable에 가깝게 다뤄야 하므로, 허용 필드만 덮어쓴 새
    Font/Fill/Alignment/Border 객체를 만들어 대입한다(8.4절 권장 방식).
    fill_color는 6자리 RRGGBB를 그대로 넘기면 openpyxl이 alpha=00으로 저장해
    배경색이 보이지 않을 수 있으므로, 적용 직전 "FF" ARGB prefix를 붙인다.
    """
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils.cell import range_boundaries

    ws = wb[change.anchor["sheet"]]
    min_col, min_row, max_col, max_row = range_boundaries(change.anchor["range"])
    patch = change.patch or {}

    font_bold = patch.get("font_bold")
    fill_color = patch.get("fill_color")
    h_align = patch.get("horizontal_alignment")
    v_align = patch.get("vertical_alignment")
    border_style = patch.get("border")

    fill = PatternFill(fgColor=f"FF{fill_color}", fill_type="solid") if fill_color is not None else None
    side = Side(style=border_style) if border_style not in (None, "none") else None

    for row in ws.iter_rows(min_row=min_row, max_row=max_row, min_col=min_col, max_col=max_col):
        for cell in row:
            if font_bold is not None:
                cell.font = Font(
                    name=cell.font.name,
                    size=cell.font.sz,
                    bold=font_bold,
                    italic=cell.font.italic,
                    color=cell.font.color,
                )
            if fill is not None:
                cell.fill = fill
            if h_align is not None or v_align is not None:
                cell.alignment = Alignment(
                    horizontal=h_align or cell.alignment.horizontal,
                    vertical=v_align or cell.alignment.vertical,
                )
            if border_style is not None:
                cell.border = Border() if border_style == "none" else Border(
                    left=side, right=side, top=side, bottom=side,
                )


# ── set_number_format ────────────────────────────────────────────────────────


def validate_xlsx_number_format_change(wb, change) -> str | None:
    """
    set_number_format change를 검증한다. 통과 시 None, 실패 시 실패 사유 문자열을 반환한다.

    검증 순서: 시트 존재 → range 문법/크기(set_cell_style과 동일 제한) → patch whitelist
    (number_format이 whitelist 안에 있는지) → expected_context 존재·셀 참조 →
    sample_values/non_empty_cells 실값 대조 (roadmap v1 6.Phase2절 "필수 설계" 기준).
    """
    sheet_name = change.anchor.get("sheet", "")
    range_ref = change.anchor.get("range", "")

    range_error, bounds = _validate_xlsx_range(wb, sheet_name, range_ref, _FORMAT_MAX_RANGE_CELLS)
    if range_error is not None:
        return range_error
    min_col, min_row, max_col, max_row = bounds

    patch = change.patch or {}
    whitelist_error = _validate_xlsx_number_format_patch_whitelist(patch)
    if whitelist_error is not None:
        return whitelist_error

    return _validate_xlsx_range_expected_context(
        wb[sheet_name], patch.get("expected_context"), "set_number_format", min_col, min_row, max_col, max_row,
    )


def _validate_xlsx_number_format_patch_whitelist(patch: dict) -> str | None:
    """patch에 허용되지 않은 키나 number_format이 whitelist 밖이면 실패 사유를 반환한다."""
    unknown_keys = set(patch.keys()) - _NUMBER_FORMAT_ALLOWED_PATCH_KEYS
    if unknown_keys:
        return f"허용되지 않은 patch 필드: {sorted(unknown_keys)}"

    number_format = patch.get("number_format")
    if not number_format:
        return "number_format이 필요합니다"
    if number_format not in _NUMBER_FORMAT_WHITELIST:
        return f"허용되지 않은 number_format: {number_format!r}"

    return None


def apply_xlsx_number_format(wb, change) -> None:
    """검증을 통과한 set_number_format change를 워크북에 적용한다. 셀 값은 건드리지 않는다."""
    from openpyxl.utils.cell import range_boundaries

    ws = wb[change.anchor["sheet"]]
    min_col, min_row, max_col, max_row = range_boundaries(change.anchor["range"])
    number_format = (change.patch or {}).get("number_format")

    for row in ws.iter_rows(min_row=min_row, max_row=max_row, min_col=min_col, max_col=max_col):
        for cell in row:
            cell.number_format = number_format


# ── set_formula ──────────────────────────────────────────────────────────────


def validate_xlsx_formula_change(wb, change) -> str | None:
    """
    set_formula change를 검증한다. 통과 시 None, 실패 시 실패 사유 문자열을 반환한다.

    1차 범위는 단일 셀 수식 설정만 허용한다 (roadmap v1 6.Phase3절) — anchor.type이
    cell_range면 range 대상이므로 무조건 거부한다.
    검증 순서: anchor.type/시트/셀 문법 → patch whitelist → formula whitelist →
    expected_context 존재·셀 참조 → sample_values/non_empty_cells 실값 대조.
    """
    from openpyxl.utils.cell import coordinate_to_tuple

    anchor_type = change.anchor.get("type", "")
    if anchor_type != "cell":
        return f"set_formula는 단일 셀(anchor.type=cell)에만 적용 가능합니다: {anchor_type!r}"

    sheet_name = change.anchor.get("sheet", "")
    cell_ref = change.anchor.get("cell", "")

    if sheet_name not in wb.sheetnames:
        return f"시트 없음: {sheet_name}"

    try:
        row, col = coordinate_to_tuple(cell_ref)
    except (ValueError, TypeError, AttributeError, KeyError):
        return f"anchor.cell 문법 오류: {cell_ref!r}"
    if not (1 <= row <= _XLSX_MAX_ROWS and 1 <= col <= _XLSX_MAX_COLUMNS):
        return f"anchor.cell이 XLSX 허용 범위를 벗어남: {cell_ref!r}"

    patch = change.patch or {}
    unknown_keys = set(patch.keys()) - _FORMULA_ALLOWED_PATCH_KEYS
    if unknown_keys:
        return f"허용되지 않은 patch 필드: {sorted(unknown_keys)}"

    formula = patch.get("formula")
    formula_error = _validate_xlsx_formula(formula)
    if formula_error is not None:
        return formula_error

    # set_formula의 expected_context는 대상 셀 자체가 아니라 수식이 참조하는 데이터
    # 범위(예: 합계 대상 B2:B10)의 현재 값을 확인하는 용도다. 대상 셀은 수식을 넣기 전이라
    # 보통 비어 있으므로, anchor.range 같은 bounds 제한 없이 시트 전체 범위에서
    # 셀 참조 문법만 검증한다 (set_cell_style/set_number_format과 달리 범위 제한이 없음).
    return _validate_xlsx_range_expected_context(
        wb[sheet_name], patch.get("expected_context"), "set_formula",
        1, 1, _XLSX_MAX_COLUMNS, _XLSX_MAX_ROWS,
    )


def _validate_xlsx_formula(formula) -> str | None:
    """
    보수적 whitelist 기반 수식 검증 (roadmap v1 6.Phase3절 "금지" 목록 기준).

    허용 함수: SUM/AVERAGE/COUNT/COUNTA/MIN/MAX/IF (중첩 호출 포함).
    금지: 외부 파일/시트 참조("!", "[", "]"), URL, 문자열 연결("&"), 암묵적 교차("@"),
    작은따옴표(시트명 quoting), 그리고 whitelist 밖의 모든 함수(INDIRECT/HYPERLINK 등).
    """
    if not isinstance(formula, str) or not formula.strip():
        return "formula는 비어 있지 않은 문자열이어야 함"

    body = formula[1:] if formula.startswith("=") else formula
    body = body.strip()
    if not body:
        return "formula가 비어 있음"

    forbidden_match = _FORMULA_FORBIDDEN_SUBSTRING_RE.search(body)
    if forbidden_match:
        return f"formula에 금지된 패턴이 포함됨 (외부 참조/URL/시트 참조 등): {formula!r}"

    if not _FORMULA_CHARSET_RE.match(body):
        return f"formula에 허용되지 않은 문자가 포함됨: {formula!r}"

    if body.count("(") != body.count(")"):
        return f"formula 괄호가 일치하지 않음: {formula!r}"

    calls = _FORMULA_FUNCTION_CALL_RE.findall(body)
    if not calls:
        return f"formula는 허용된 함수 호출을 포함해야 함: {formula!r}"

    for name in calls:
        upper = name.upper()
        if upper in _FORMULA_FORBIDDEN_FUNCTIONS:
            return f"금지된 함수: {name}"
        if upper not in _FORMULA_ALLOWED_FUNCTIONS:
            return f"알 수 없거나 허용되지 않은 함수: {name}"

    token_error = _validate_xlsx_formula_tokens(body, formula)
    if token_error is not None:
        return token_error

    # 함수명·셀참조·불리언 리터럴을 모두 제거했을 때 남는 알파벳이 있으면
    # whitelist를 우회하는 미확인 토큰(연산자로 위장한 이름 등)으로 간주해 거부한다.
    remainder = _FORMULA_FUNCTION_CALL_RE.sub("(", body)
    remainder = _FORMULA_CELL_REF_RE.sub("_", remainder)
    remainder = _FORMULA_LITERAL_RE.sub("_", remainder)
    if re.search(r"[A-Za-z]", remainder):
        return f"formula에 알 수 없는 토큰이 포함됨: {formula!r}"

    return None


def _validate_xlsx_formula_tokens(body: str, formula: str) -> str | None:
    """
    openpyxl 토크나이저로 수식의 큰 형태를 한 번 더 제한한다.

    정규식 whitelist가 놓칠 수 있는 `=SUM(A1:A2) B1`, `=SUM(A1:A2)A1`,
    `=SUM(A1 A2)` 같은 trailing/adjacent/intersection 참조를 차단한다.
    """
    try:
        from openpyxl.formula.tokenizer import Tokenizer

        raw_tokens = Tokenizer(f"={body}").items
    except Exception as exc:
        return f"formula 토큰화 실패: {exc}"

    def is_value_start(token) -> bool:
        return (
            token.type == "OPERAND"
            or (token.type == "FUNC" and token.subtype == "OPEN")
            or (token.type == "PAREN" and token.subtype == "OPEN")
        )

    def is_value_end(token) -> bool:
        return (
            token.type == "OPERAND"
            or (token.type == "FUNC" and token.subtype == "CLOSE")
            or (token.type == "PAREN" and token.subtype == "CLOSE")
        )

    tokens = []
    for idx, token in enumerate(raw_tokens):
        if token.type != "WHITE-SPACE":
            tokens.append(token)
            continue

        prev_token = next((t for t in reversed(raw_tokens[:idx]) if t.type != "WHITE-SPACE"), None)
        next_token = next((t for t in raw_tokens[idx + 1:] if t.type != "WHITE-SPACE"), None)
        if prev_token is not None and next_token is not None:
            if is_value_end(prev_token) and is_value_start(next_token):
                return f"formula 토큰 사이에 연산자 또는 구분자가 필요함: {formula!r}"

    if not tokens:
        return f"formula가 비어 있음: {formula!r}"

    first = tokens[0]
    if first.type != "FUNC" or first.subtype != "OPEN":
        return f"formula는 허용된 함수 호출로 시작해야 함: {formula!r}"
    if not is_value_end(tokens[-1]):
        return f"formula가 완결된 값 표현식으로 끝나야 함: {formula!r}"

    depth = 0
    for idx, token in enumerate(tokens):
        if token.type == "FUNC" and token.subtype == "OPEN":
            depth += 1
        elif token.type == "FUNC" and token.subtype == "CLOSE":
            depth -= 1
            if depth < 0:
                return f"formula 괄호가 일치하지 않음: {formula!r}"
        elif token.type == "PAREN" and token.subtype == "OPEN":
            depth += 1
        elif token.type == "PAREN" and token.subtype == "CLOSE":
            depth -= 1
            if depth < 0:
                return f"formula 괄호가 일치하지 않음: {formula!r}"
        elif token.type == "SEP" and depth <= 0:
            return f"formula 인자 구분자는 함수 내부에서만 허용됨: {formula!r}"
        elif token.type == "OPERATOR-INFIX" and token.value == ",":
            return f"formula 인자 구분자는 함수 내부에서만 허용됨: {formula!r}"
        elif token.type == "OPERAND" and token.subtype == "RANGE":
            if str(token.value).startswith(":") or str(token.value).endswith(":"):
                return f"formula 셀 범위 문법 오류: {formula!r}"

        if idx > 0:
            prev = tokens[idx - 1]
            if is_value_end(prev) and is_value_start(token):
                return f"formula 토큰 사이에 연산자 또는 구분자가 필요함: {formula!r}"
            if token.type == "OPERATOR-INFIX":
                if not is_value_end(prev):
                    return f"formula 연산자 위치 오류: {formula!r}"
                next_token = tokens[idx + 1] if idx + 1 < len(tokens) else None
                if next_token is None or not is_value_start(next_token):
                    return f"formula 연산자 위치 오류: {formula!r}"
            if token.type == "SEP":
                if not is_value_end(prev):
                    return f"formula 인자 구분자 위치 오류: {formula!r}"
                next_token = tokens[idx + 1] if idx + 1 < len(tokens) else None
                if next_token is None or not is_value_start(next_token):
                    return f"formula 인자 구분자 위치 오류: {formula!r}"

    if depth != 0:
        return f"formula 괄호가 일치하지 않음: {formula!r}"

    return None


def apply_xlsx_formula(wb, change) -> None:
    """검증을 통과한 set_formula change를 워크북 단일 셀에 적용한다."""
    ws = wb[change.anchor["sheet"]]
    formula = (change.patch or {}).get("formula")
    if not formula.startswith("="):
        formula = f"={formula}"
    ws[change.anchor["cell"]] = formula


def render_docx(original_bytes: bytes, changes: list) -> PatchResult:
    """
    DOCX bytes + applied change 목록 → PatchResult.

    replace_text operation: anchor.text_match 문자열을 포함하는 단락을 찾아
    run 재구성 방식으로 교체한다. 일치 단락 없으면 failed_items에 기록.

    변형 전에 문서 전체(단락 단위)의 text_match 발생 횟수를 먼저 센다 —
    같은 문구가 2번 이상 나오면 첫 번째를 조용히 바꾸는 대신
    needs_confirmation_items(code=ambiguous_anchor)로 멈춘다
    (design v1 10.1절 "DOCX 다중 매치 침묵 처리 수정", render_pdf의
    AnchorResolver AMBIGUOUS와 동일한 UX).

    주의: 첫 번째 run의 서식을 유지하고 나머지 run을 비우는 방식이므로
          교체 후 폰트·크기는 첫 번째 run 서식을 따른다.
    """
    try:
        from docx import Document
    except ImportError:
        return PatchResult(
            b"",
            [],
            [{"operation_id": c.operation_id, "reason": "python-docx 미설치"} for c in changes],
        )

    try:
        doc = Document(io.BytesIO(original_bytes))
    except Exception as exc:
        return PatchResult(
            b"",
            [],
            [{"operation_id": c.operation_id, "reason": f"DOCX 로드 실패: {exc}"} for c in changes],
        )

    applied_ids: list[str] = []
    failed_items: list[dict] = []
    needs_confirmation_items: list[dict] = []

    for change in changes:
        target_text = change.anchor.get("text_match", "")

        # 빈 text_match는 모든 단락에 "매치"되어 임의 위치 삽입으로 이어지므로
        # 발생 횟수를 세기 전에 명시적으로 실패시킨다.
        if not target_text:
            failed_items.append({
                "operation_id": change.operation_id,
                "reason": "anchor.text_match가 비어 있음",
            })
            logger.warning("render_docx: text_match 비어 있음 | op=%s", change.operation_id)
            continue

        # 변형 전에 전체 발생 횟수를 센다 — 단락 간 중복과 단락 내 중복 모두 포함.
        matched_para = None
        occurrence_count = 0
        for para in doc.paragraphs:
            full_text = "".join(run.text for run in para.runs)
            count = full_text.count(target_text)
            if count and matched_para is None:
                matched_para = para
            occurrence_count += count

        if occurrence_count == 0:
            failed_items.append({
                "operation_id": change.operation_id,
                "reason": f"대상 텍스트 없음: {target_text!r}",
            })
            logger.warning("render_docx: 대상 텍스트 없음 | op=%s | text_match=%r", change.operation_id, target_text)
            continue

        if occurrence_count > 1:
            needs_confirmation_items.append({
                "operation_id": change.operation_id,
                "reason": f"{target_text!r}에 대해 {occurrence_count}개의 매치가 있어 위치 확인이 필요함",
                "code": FAILURE_CODE_AMBIGUOUS_ANCHOR,
            })
            logger.warning(
                "render_docx: text_match 다중 매치 | op=%s | text_match=%r | count=%d",
                change.operation_id, target_text, occurrence_count,
            )
            continue

        # 유일 매치 — 기존 교체 동작 (첫 run에 전체 텍스트를 싣고 나머지 run 비움)
        full_text = "".join(run.text for run in matched_para.runs)
        new_text = full_text.replace(target_text, change.replacement, 1)
        if matched_para.runs:
            matched_para.runs[0].text = new_text
            for run in matched_para.runs[1:]:
                run.text = ""
        applied_ids.append(change.operation_id)

    if not applied_ids:
        return PatchResult(b"", [], failed_items, needs_confirmation_items)

    output = io.BytesIO()
    doc.save(output)
    return PatchResult(output.getvalue(), applied_ids, failed_items, needs_confirmation_items)


def render_pptx(original_bytes: bytes, changes: list) -> PatchResult:
    """
    PPTX bytes + applied change 목록 → PatchResult.

    replace_text operation: anchor.slide_index(0-based), anchor.shape_index(0-based),
    anchor.text_match 로 대상 텍스트를 특정해 교체한다.
    슬라이드·셰이프 범위 초과, 텍스트 없음 → failed_items에 기록.
    """
    try:
        from pptx import Presentation
    except ImportError:
        return PatchResult(
            b"",
            [],
            [{"operation_id": c.operation_id, "reason": "python-pptx 미설치"} for c in changes],
        )

    try:
        prs = Presentation(io.BytesIO(original_bytes))
    except Exception as exc:
        return PatchResult(
            b"",
            [],
            [{"operation_id": c.operation_id, "reason": f"PPTX 로드 실패: {exc}"} for c in changes],
        )

    applied_ids: list[str] = []
    failed_items: list[dict] = []

    for change in changes:
        slide_index = change.anchor.get("slide_index", 0)
        shape_index = change.anchor.get("shape_index")
        target_text = change.anchor.get("text_match", "")

        if slide_index >= len(prs.slides):
            failed_items.append({
                "operation_id": change.operation_id,
                "reason": f"슬라이드 인덱스 초과: {slide_index}",
            })
            continue

        slide = prs.slides[slide_index]

        if shape_index is not None and shape_index >= len(slide.shapes):
            failed_items.append({
                "operation_id": change.operation_id,
                "reason": f"셰이프 인덱스 초과: {shape_index}",
            })
            continue

        shapes = [slide.shapes[shape_index]] if shape_index is not None else list(slide.shapes)

        replaced = False
        for shape in shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    full_text = "".join(run.text for run in para.runs)
                    if target_text not in full_text:
                        continue
                    new_text = full_text.replace(target_text, change.replacement, 1)
                    if para.runs:
                        para.runs[0].text = new_text
                        for run in para.runs[1:]:
                            run.text = ""
                    replaced = True
                    break

            if replaced:
                break

            if shape.has_table:
                for row in shape.table.rows:
                    for cell in row.cells:
                        if target_text not in cell.text:
                            continue
                        tf = cell.text_frame
                        for para in tf.paragraphs:
                            full_text = "".join(run.text for run in para.runs)
                            if target_text not in full_text:
                                continue
                            new_text = full_text.replace(target_text, change.replacement, 1)
                            if para.runs:
                                para.runs[0].text = new_text
                                for run in para.runs[1:]:
                                    run.text = ""
                            replaced = True
                            break
                        if replaced:
                            break
                    if replaced:
                        break

        if not replaced:
            failed_items.append({
                "operation_id": change.operation_id,
                "reason": f"대상 텍스트 없음: {target_text!r}",
            })
            continue

        applied_ids.append(change.operation_id)

    if not applied_ids:
        return PatchResult(b"", [], failed_items)

    output = io.BytesIO()
    prs.save(output)
    return PatchResult(output.getvalue(), applied_ids, failed_items)


def render_pdf(original_bytes: bytes, changes: list) -> PatchResult:
    """
    PDF bytes + applied change 목록 → PatchResult.

    annotate/redact_overlay operation: AnchorResolver로 anchor를 해석하고 페이지에
    적용한다. RESOLVED만 실제로 렌더링하며, AMBIGUOUS(후보 여러 개)는
    needs_confirmation_items로, NOT_FOUND/UNSUPPORTED는 failed_items로 분리한다
    (anchor_resolution.py — "모호하면 자동 반영하지 않는다" 원칙).

    적용 후에는 수정본 bytes를 다시 열어 구조적 invariant를 검증한다
    (design v1 7.1절 1~2항, _validate_pdf_render). 검증 실패 시 artifact를
    내보내지 않고 applied였던 항목을 code=render_validation_failed로 failed 처리한다.
    """
    try:
        import fitz
    except ImportError:
        return PatchResult(
            b"",
            [],
            [{"operation_id": c.operation_id, "reason": "PyMuPDF(fitz) 미설치"} for c in changes],
        )

    try:
        doc = fitz.open(stream=original_bytes, filetype="pdf")
    except Exception as exc:
        return PatchResult(
            b"",
            [],
            [{"operation_id": c.operation_id, "reason": f"PDF 로드 실패: {exc}"} for c in changes],
        )

    from .anchor_resolution import AnchorResolver, AnchorStatus, build_pdf_document_layout

    layout = build_pdf_document_layout(doc)
    resolver = AnchorResolver()

    applied_ids: list[str] = []
    failed_items: list[dict] = []
    needs_confirmation_items: list[dict] = []
    # 검증 단계에서 change별 rect·페이지를 다시 쓰기 위해 적용 이력을 보존한다
    applied_records: list[dict] = []

    for change in changes:
        result = resolver.resolve(change.anchor, layout)

        if result.status == AnchorStatus.RESOLVED:
            page = doc[result.page]
            if change.operation == "annotate":
                _apply_pdf_annotate(page, result.rect, change)
            else:
                _apply_pdf_redact_overlay(page, result.rect, change)
            applied_ids.append(change.operation_id)
            applied_records.append({"change": change, "page": result.page, "rect": result.rect})
        elif result.status == AnchorStatus.AMBIGUOUS:
            needs_confirmation_items.append({
                "operation_id": change.operation_id,
                "reason": result.reason,
                "code": FAILURE_CODE_AMBIGUOUS_ANCHOR,
            })
            logger.warning(
                "render_pdf: anchor 후보 다수 | op=%s | reason=%s", change.operation_id, result.reason,
            )
        else:
            reason = result.reason or f"PDF anchor 해석 실패: {change.anchor}"
            failed_items.append({"operation_id": change.operation_id, "reason": reason})
            logger.warning(
                "render_pdf: anchor 해석 실패 | op=%s | status=%s | reason=%s",
                change.operation_id, result.status, reason,
            )

    if not applied_ids:
        doc.close()
        return PatchResult(b"", [], failed_items, needs_confirmation_items)

    output = io.BytesIO()
    doc.save(output)
    doc.close()
    output.seek(0)
    output_bytes = output.read()

    # post-render 검증 — 하나라도 실패하면 artifact 전체를 내보내지 않는다.
    # 수정본 bytes에는 모든 applied change의 변형이 섞여 있어 실패 항목만
    # 떼어낼 수 없기 때문이다(부분 성공 불가).
    validation_failures = _validate_pdf_render(layout, output_bytes, applied_records)
    if validation_failures:
        failure_by_id = {item["operation_id"]: item for item in validation_failures}
        for record in applied_records:
            op_id = record["change"].operation_id
            failed_items.append(failure_by_id.get(op_id) or {
                "operation_id": op_id,
                "reason": "같은 결과물의 다른 변경이 render 검증에 실패해 함께 중단됨",
                "code": FAILURE_CODE_RENDER_VALIDATION_FAILED,
            })
        return PatchResult(b"", [], failed_items, needs_confirmation_items)

    return PatchResult(output_bytes, applied_ids, failed_items, needs_confirmation_items)


def render_hwp(original_bytes: bytes, changes: list) -> PatchResult:
    """
    HWP bytes + applied change 목록 → PatchResult.

    subprocess로 hwp_worker.mjs를 호출한다. subprocess 실패·타임아웃 시
    예외를 전파하지 않고 PatchResult(b"", [], all_failed) 형태로 반환한다.
    (업무 실패 — Result 패턴)
    """
    if not changes:
        return PatchResult(b"", [], [])

    from django.conf import settings

    input_b64 = base64.b64encode(original_bytes).decode()
    payload = {
        "input_b64": input_b64,
        "changes": [
            {
                "operation_id": c.operation_id,
                "original": c.original,
                "replacement": c.replacement,
                "anchor": c.anchor,
            }
            for c in changes
        ],
    }

    node_bin = os.environ.get("NODE_PATH", "node")
    project_root = settings.BASE_DIR.parent
    worker_path = "backend/workers/hwp_worker.mjs"

    def _all_failed(reason: str) -> PatchResult:
        return PatchResult(
            b"",
            [],
            [{"operation_id": c.operation_id, "reason": reason} for c in changes],
        )

    try:
        result = subprocess.run(
            [node_bin, worker_path],
            input=json.dumps(payload).encode(),
            capture_output=True,
            timeout=30,
            cwd=str(project_root),
        )
    except subprocess.TimeoutExpired:
        logger.error("render_hwp: HWP worker 타임아웃")
        return _all_failed("HWP worker 타임아웃 (30초 초과)")
    except Exception as exc:
        logger.error("render_hwp: HWP worker 실행 실패 | %s", exc)
        return _all_failed(f"HWP worker 실행 실패: {exc}")

    if result.returncode != 0:
        stderr_msg = result.stderr.decode(errors="replace").strip()
        logger.error("render_hwp: worker 비정상 종료 | returncode=%s | stderr=%s", result.returncode, stderr_msg)
        return _all_failed(f"HWP worker 오류: {stderr_msg}")

    try:
        output = json.loads(result.stdout.decode())
    except Exception as exc:
        return _all_failed(f"HWP worker 출력 파싱 실패: {exc}")

    applied_ids: list[str] = output.get("applied", [])
    failed_items: list[dict] = output.get("failed", [])

    if not applied_ids:
        return PatchResult(b"", [], failed_items)

    try:
        hwp_bytes = base64.b64decode(output["output_b64"])
    except Exception as exc:
        return _all_failed(f"HWP worker output_b64 디코딩 실패: {exc}")

    return PatchResult(hwp_bytes, applied_ids, failed_items)


# ── 3단계: persist — DB + storage 갱신 ─────────────────────────────────────────

def persist_patch_result(version, result: PatchResult, ext: str, changes: list) -> None:
    """
    패치 결과를 DB와 storage에 반영한다.

    - failed_items에 해당하는 DocumentChange.status를 FAILED로 갱신
    - needs_confirmation_items에 해당하는 DocumentChange.status를 NEEDS_CONFIRMATION으로 갱신
      (자동 반영하지 않고 사용자 확인을 기다리는 상태 — FAILED와 구분)
    - version.needs_confirmation_change_ids는 version.status가 READY/FAILED/NEEDS_CONFIRMATION
      무엇으로 끝나든 항상 needs_confirmation_items 기준으로 갱신한다 — 프론트가 버전 상태와
      무관하게 "어떤 change가 확인이 필요한지" 조회할 수 있어야 한다(applied_change_ids와 대칭)
    - applied_ids가 비어있고 needs_confirmation_items만 있으면 version.status = NEEDS_CONFIRMATION
    - applied_ids가 비어있고 failed_items가 있으면 version.status = FAILED
    - applied_ids가 있으면:
        artifact_file을 storage에 저장 (인프라 경계 — try/except 격리)
        version.applied_change_ids, version.status = READY 갱신
    """
    from django.core.files.base import ContentFile
    from .models import DocumentChange, DocumentVersion

    failed_op_ids = {item["operation_id"] for item in result.failed_items}
    needs_confirmation_op_ids = {item["operation_id"] for item in result.needs_confirmation_items}
    for change in changes:
        if change.operation_id in failed_op_ids:
            change.status = DocumentChange.Status.FAILED
            change.save(update_fields=["status", "updated_at"])
        elif change.operation_id in needs_confirmation_op_ids:
            change.status = DocumentChange.Status.NEEDS_CONFIRMATION
            change.save(update_fields=["status", "updated_at"])

    # needs_confirmation_change_ids는 version.status(READY/FAILED/NEEDS_CONFIRMATION 중
    # 어느 것으로 끝나든)와 무관하게 항상 최신으로 반영한다 — 프론트가 "실패"와 "위치 확인
    # 필요"를 구분하려면 이 값이 필요하다(READY로 끝나는 부분 성공 케이스뿐 아니라
    # 버전 전체가 NEEDS_CONFIRMATION/FAILED로 끝나는 아래 이른 반환 경로에서도 마찬가지다).
    version.needs_confirmation_change_ids = sorted(needs_confirmation_op_ids)

    if not result.applied_ids:
        # needs_confirmation만 있고 hard failure가 없으면 "위치 확인 필요"로 구분한다.
        if result.needs_confirmation_items and not result.failed_items:
            reason = "; ".join(item["reason"] for item in result.needs_confirmation_items)
            _set_needs_confirmation(version, reason)
            return
        # failed_items에 구체적 실패 사유가 있으면 그것을 error_message로 사용한다.
        # 없으면 generic 메시지를 쓴다(예: changes 자체가 없는 경우).
        if result.failed_items:
            reason = "; ".join(item["reason"] for item in result.failed_items)
        else:
            reason = "적용 가능한 변경 항목이 없습니다."
        _set_failed(version, reason)
        return

    # artifact_file 저장 — storage I/O 실패는 인프라 경계이므로 try/except로 격리
    try:
        version.artifact_file.save(
            f"v{version.pk}.{ext}",
            ContentFile(result.output_bytes),
            save=False,
        )
        version.artifact_format = ext
    except Exception as exc:
        logger.exception("persist_patch_result: artifact_file 저장 실패 | version_id=%s", version.pk)
        _set_failed(version, f"결과 파일 저장 실패: {exc}")
        return

    version.applied_change_ids = result.applied_ids
    version.status = DocumentVersion.Status.READY
    version.save(update_fields=[
        "artifact_file", "artifact_format", "applied_change_ids",
        "needs_confirmation_change_ids", "status", "updated_at",
    ])


# ── 내부 헬퍼 (render_pdf 전용) ──────────────────────────────────────────────

def _set_failed(version, error_message: str) -> None:
    """
    version 상태를 FAILED로 설정하고 에러 메시지를 저장한다.

    needs_confirmation_change_ids도 함께 저장한다 — persist_patch_result가 이 함수를
    부르기 전에 그 필드를 이미 인스턴스에 설정해뒀을 수 있고(예: needs_confirmation과
    failed가 섞여 결국 FAILED로 끝나는 경우), tasks.py의 다른 이른 실패 경로(파일 없음
    등)처럼 손대지 않은 경우엔 update_fields에 있어도 기존 값을 그대로 다시 쓸 뿐이라
    안전하다.
    """
    from .models import DocumentVersion
    version.status = DocumentVersion.Status.FAILED
    version.error_message = error_message
    version.save(update_fields=["status", "error_message", "needs_confirmation_change_ids", "updated_at"])


def _set_needs_confirmation(version, error_message: str) -> None:
    """version 상태를 NEEDS_CONFIRMATION으로 설정한다 — FAILED와 달리 재시도가 아니라 사용자 확인이 필요함을 의미한다."""
    from .models import DocumentVersion
    version.status = DocumentVersion.Status.NEEDS_CONFIRMATION
    version.error_message = error_message
    version.save(update_fields=["status", "error_message", "needs_confirmation_change_ids", "updated_at"])


def _resolve_pdf_rect(doc, anchor: dict):
    """
    anchor 딕셔너리에서 (0-based 페이지 인덱스, fitz.Rect)를 반환하는 하위호환 래퍼.

    실제 해석은 anchor_resolution.AnchorResolver가 담당한다(모듈 상단 주석 참고).
    RESOLVED가 아니면(AMBIGUOUS 포함) None을 반환한다 — render_pdf는 이 래퍼를
    거치지 않고 resolver를 직접 호출해 AMBIGUOUS/NOT_FOUND를 구분하지만, 이
    함수는 단순 조회용으로 남겨둔 하위호환 지점이다.
    """
    from .anchor_resolution import AnchorResolver, AnchorStatus, build_pdf_document_layout

    layout = build_pdf_document_layout(doc)
    result = AnchorResolver().resolve(anchor, layout)
    if result.status != AnchorStatus.RESOLVED:
        return None
    return (result.page, result.rect)


def _apply_pdf_annotate(page, rect, change) -> None:
    """지정 rect에 하이라이트 주석을 추가한다."""
    comment = change.replacement or getattr(change, "reason", "") or ""
    annot = page.add_highlight_annot(rect)
    annot.set_info(content=comment)
    annot.update()


# 한글 replacement 렌더링용 임베드 폰트 — Noto Sans KR Regular(TrueType)를
# 한글·라틴·기본 문장부호로 서브셋한 파일 (backend/apps/documents/fonts/README.md 참조)
_KOREAN_FONT_PATH = Path(__file__).resolve().parent / "fonts" / "NotoSansKR-Regular.ttf"
_KOREAN_FONT_NAME = "NotoSansKR"


def _apply_pdf_redact_overlay(page, rect, change) -> None:
    """
    지정 rect 영역을 흰색으로 가린 뒤 replacement 텍스트를 overlay로 삽입한다.

    CJK 문자 포함 시 NotoSansKR을 페이지에 임베드해 사용하고, 순수 ASCII는
    "helv"를 유지한다(korea-s/임베드 폰트로 ASCII를 그리면 문자 사이에
    불필요한 폭이 생겨 텍스트 추출 시 공백이 끼는 부작용이 있다).

    PyMuPDF 내장 fontname="korea-s"는 실제 글리프를 PDF에 담지 않는
    "참조 전용" 폰트다(뷰어가 시스템에 Batang 폰트를 갖고 있다고 가정) —
    Adobe 등 데스크톱 뷰어는 시스템 폰트로 대체해 보여주지만, 브라우저
    pdf.js는 대체하지 못해 텍스트가 완전히 투명하게 렌더링된다.
    page.insert_font(fontfile=...)로 실제 글리프 데이터를 PDF에 임베드하면
    어떤 뷰어에서도 동일하게 보인다.
    """
    page.add_redact_annot(rect, fill=(1, 1, 1))
    page.apply_redactions()

    font_size = change.patch.get("font_size", 11) if change.patch else 11
    replacement = change.replacement or ""
    is_cjk = any(ord(ch) > 127 for ch in replacement)

    if is_cjk:
        fontname = _KOREAN_FONT_NAME
        page.insert_font(fontname=fontname, fontfile=str(_KOREAN_FONT_PATH))
    else:
        fontname = "helv"

    page.insert_text(
        (rect.x0, rect.y1 - 2),
        replacement,
        fontsize=font_size,
        fontname=fontname,
        color=(0, 0, 0),
    )


# ── render_pdf post-render 검증 (design v1 7.1절 invariant 1~2 — 베타 전 smoke check) ──

def _validate_pdf_render(layout, output_bytes: bytes, applied_records: list[dict]) -> list[dict]:
    """
    수정본 PDF의 구조적 invariant를 검증한다. 실패 항목 목록(failed_items 형식)을
    반환하며 빈 목록이면 통과다.

    검증 순서 (구체적인 사유를 먼저 보고하도록 배치):
      1. 수정본이 예외 없이 열리고 페이지 수가 유지되는지 (invariant 2)
      2. redact/replace 계열 change마다 replacement가 rect 근처에서 재추출되고
         original이 그 자리에서 사라졌는지 (invariant 1) — build_pdf_document_layout의
         token 추출을 그대로 재사용해 PR #29~#31이 고친 버그 클래스를 재검증한다
      3. 원래 텍스트가 있던 페이지가 예상 밖으로 비지 않았는지 (invariant 2)

    invariant 3~4(rect 겹침·과대 redact 영역)는 베타 후 범위다 (design v1 10.2절).
    """
    import fitz

    from .anchor_resolution import build_pdf_document_layout

    def _all_failed(reason: str) -> list[dict]:
        return [
            {
                "operation_id": record["change"].operation_id,
                "reason": reason,
                "code": FAILURE_CODE_RENDER_VALIDATION_FAILED,
            }
            for record in applied_records
        ]

    try:
        modified = fitz.open(stream=output_bytes, filetype="pdf")
    except Exception as exc:
        # 렌더 산출물 자체가 열리지 않음 — 라이브러리 경계 실패도 검증 실패로 수렴시킨다
        return _all_failed(f"render 검증 실패: 수정본 PDF를 열 수 없음 ({exc})")

    try:
        if len(modified) != len(layout.pages):
            return _all_failed(
                f"render 검증 실패: 페이지 수가 변함 (원본 {len(layout.pages)} → 수정본 {len(modified)})"
            )

        modified_layout = build_pdf_document_layout(modified)

        failures: list[dict] = []
        for record in applied_records:
            change = record["change"]
            # annotate는 텍스트를 바꾸지 않으므로 invariant 1 대상이 아니다
            if change.operation == "annotate":
                continue
            reason = _validate_pdf_text_change(
                modified_layout.pages[record["page"]],
                record["rect"],
                change,
                modified[record["page"]].rect,
            )
            if reason is not None:
                failures.append({
                    "operation_id": change.operation_id,
                    "reason": reason,
                    "code": FAILURE_CODE_RENDER_VALIDATION_FAILED,
                })
                logger.warning(
                    "render_pdf: 검증 실패 | op=%s | reason=%s", change.operation_id, reason,
                )
        if failures:
            return failures

        empty_page_reason = _find_unexpected_empty_page(
            layout.pages, modified_layout.pages, applied_records,
        )
        if empty_page_reason is not None:
            logger.warning("render_pdf: 검증 실패 | reason=%s", empty_page_reason)
            return _all_failed(empty_page_reason)
        return []
    finally:
        modified.close()


def _validate_pdf_text_change(page_tokens: list, rect, change, page_rect) -> str | None:
    """
    invariant 1: replacement가 rect 근처(같은 줄 대역)에서 재추출되고 original은
    rect 자리에서 사라졌는지 확인한다. 통과 시 None, 실패 시 사유 문자열.

    비교는 공백을 제거한 문자열로 한다 — token 결합 시 공백 규칙이 문서마다 달라
    (anchor_resolution._build_nospace_index와 동일한 이유) 공백 차이 오탐을 막는다.
    """
    import fitz

    replacement = _strip_whitespace(change.replacement or "")
    original = _strip_whitespace(change.original or change.anchor.get("target_text") or "")
    font_size = change.patch.get("font_size", 11) if change.patch else 11

    if replacement:
        # 삽입 텍스트는 (rect.x0, rect.y1-2) 기준으로 오른쪽으로 그려지므로 오른쪽
        # 경계는 페이지 끝까지 여유 있게 잡는다 (같은 줄 대역 overapproximation).
        band = fitz.Rect(rect.x0 - 2, rect.y0 - font_size, page_rect.x1, rect.y1 + font_size)
        band_text = _strip_whitespace(_tokens_text_in_clip(page_tokens, band))
        if replacement not in band_text:
            return (
                f"render 검증 실패: replacement {change.replacement!r}가 수정 위치 근처에서 "
                "추출되지 않음 (텍스트가 실제로 그려지지 않았을 가능성)"
            )

    # replacement가 original을 포함하면(예: '6' → '6월') 잔존처럼 보이는 오탐을
    # 피할 수 없으므로 그 경우에만 잔존 확인을 건너뛴다.
    if original and original not in replacement:
        local = fitz.Rect(rect.x0 - 2, rect.y0 - 2, rect.x1 + 2, rect.y1 + 2)
        local_text = _strip_whitespace(_tokens_text_in_clip(page_tokens, local))
        if original in local_text:
            return (
                f"render 검증 실패: original {change.original!r}이(가) 수정 위치에 "
                "여전히 남아 있음 (redaction 누락 가능성)"
            )

    return None


def _find_unexpected_empty_page(
    original_pages: list, modified_pages: list, applied_records: list[dict],
) -> str | None:
    """
    invariant 2: 원래 텍스트가 있던 페이지가 수정 후 비어 있으면 사유를 반환한다.

    replacement가 빈 문자열인 redact(텍스트 삭제 목적)가 적용된 페이지는
    의도적으로 비었을 수 있으므로 검사에서 제외한다.
    """
    exempt_pages = {
        record["page"]
        for record in applied_records
        if record["change"].operation != "annotate" and not (record["change"].replacement or "")
    }
    for page_idx, original_tokens in enumerate(original_pages):
        if not original_tokens or page_idx in exempt_pages:
            continue
        if page_idx < len(modified_pages) and not modified_pages[page_idx]:
            return f"render 검증 실패: {page_idx + 1}페이지가 수정 후 예상 밖으로 비어 있음"
    return None


def _strip_whitespace(text: str) -> str:
    """모든 공백 문자를 제거한다 (token 결합 방식과 무관한 비교용)."""
    return re.sub(r"\s+", "", text)


def _tokens_text_in_clip(page_tokens: list, clip) -> str:
    """clip 영역과 겹치는 token들의 텍스트를 읽기순서 그대로 공백 없이 이어붙인다."""
    import fitz

    return "".join(t.text for t in page_tokens if fitz.Rect(t.bbox).intersects(clip))
