"""
change_highlights 계약 생성 헬퍼.

change_highlights 항목 스키마:
  id          : React key 및 팝업 동기화용 안정 문자열
  kind        : correction | patch | masking | analysis
  target      : cell | slide | page | shape | table_cell | text
  format      : xlsx | csv | pptx | docx | pdf | hwp | image
  slide_index : 슬라이드 0-based 인덱스 (PPTX 전용)
  shape_index : 셰이프 순번 (PPTX 전용)
  row_index   : 테이블 행 (table_cell 전용)
  col_index   : 테이블 열 (table_cell 전용)
  cell        : 셀 좌표 문자열 (스프레드시트 전용, ex: "D12")
  sheet       : 시트명 (스프레드시트 전용)
  original    : 변경 전 텍스트
  corrected   : 변경 후 텍스트
  summary     : 요약 설명
  severity    : info | warning | error
  source      : analysis | artifact | manual_patch
"""
from __future__ import annotations


def corrections_to_change_highlights(
    corrections: list,
    upload_log_id: int | None = None,
    fmt: str = "xlsx",
) -> list:
    """
    snippet_data.corrections 리스트를 change_highlights 계약으로 변환한다.
    corrections 항목: {"cell": "D12", "original": "...", "corrected": "...", ...}
    """
    highlights = []
    uid = upload_log_id or 0
    for i, c in enumerate(corrections):
        highlights.append({
            "id":        f"correction-{uid}-{i}",
            "kind":      "correction",
            "target":    "cell",
            "format":    fmt,
            "cell":      c.get("cell", ""),
            "sheet":     c.get("sheet", ""),
            "original":  c.get("original", ""),
            "corrected": c.get("corrected", ""),
            "summary":   c.get("summary", ""),
            "severity":  c.get("severity", "info"),
            "source":    "analysis",
        })
    return highlights


def patches_to_change_highlights(patches: list, upload_log_id: int) -> list:
    """
    PptxPatchView 적용 패치 목록을 change_highlights 계약으로 변환한다.
    patches 항목: {"slide_index": 0, "shape_index": 0, "type": "text",
                   "new_text": "...", "_original": "원본 텍스트"}
    """
    highlights = []
    for i, patch in enumerate(patches):
        slide_idx  = int(patch.get("slide_index", 0))
        shape_idx  = int(patch.get("shape_index", 0))
        patch_type = patch.get("type", "text")

        # table_cell은 target을 명시적으로 구분한다
        target = "table_cell" if patch_type == "table_cell" else "shape"

        entry: dict = {
            "id":          f"patch-{upload_log_id}-{slide_idx}-{shape_idx}-{i}",
            "kind":        "patch",
            "target":      target,
            "format":      "pptx",
            "slide_index": slide_idx,
            "shape_index": shape_idx,
            "original":    patch.get("_original", ""),
            "corrected":   str(patch.get("new_text", "")),
            "source":      "manual_patch",
        }
        if patch_type == "table_cell":
            entry["row_index"] = int(patch.get("row_index", 0))
            entry["col_index"] = int(patch.get("col_index", 0))

        highlights.append(entry)
    return highlights
