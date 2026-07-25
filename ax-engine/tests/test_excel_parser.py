import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import openpyxl

from parsers.excel_parser import extract_sheet_preview


def _build_xlsx(rows: list[list]) -> str:
    """임시 xlsx 파일을 만들어 경로를 반환한다."""
    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    fd, path = tempfile.mkstemp(suffix=".xlsx")
    os.close(fd)
    wb.save(path)
    return path


class TestExtractSheetPreview(unittest.TestCase):
    def setUp(self):
        self._tmp_files: list[str] = []

    def tearDown(self):
        for p in self._tmp_files:
            Path(p).unlink(missing_ok=True)

    def _make(self, rows: list[list]) -> str:
        path = _build_xlsx(rows)
        self._tmp_files.append(path)
        return path

    def test_first_row_becomes_headers_rest_becomes_preview_rows(self):
        """
        [버그 수정] 패치 적용 전(artifact 없는) 최초 분석에서도 "시트 미리보기"
        패널에 실제 시트 데이터가 보여야 한다 — 그러려면 최초 분석 단계에서부터
        headers/preview_rows를 실제로 추출해야 한다.
        """
        path = self._make([
            ["날짜", "품목", "수량"],
            ["2026-01-03", "사무용품A", 10],
            ["2026-01-10", "사무용품B", 5],
        ])

        result = extract_sheet_preview(path)

        self.assertEqual(result["headers"], ["날짜", "품목", "수량"])
        self.assertEqual(result["preview_rows"], [
            ["2026-01-03", "사무용품A", 10],
            ["2026-01-10", "사무용품B", 5],
        ])

    def test_empty_cells_become_empty_string_not_none(self):
        """빈 셀은 None이 아니라 빈 문자열로 나와야 프론트 렌더링이 깨지지 않는다."""
        path = self._make([
            ["회사명", "주소", "TEL"],
            [None, None, None],
        ])

        result = extract_sheet_preview(path)

        self.assertEqual(result["preview_rows"], [["", "", ""]])

    def test_max_rows_limits_preview_size(self):
        """행이 많은 시트에서도 max_rows만큼만 잘라 응답 크기를 제한한다."""
        rows = [["h1", "h2"]] + [[f"r{i}", i] for i in range(100)]
        path = self._make(rows)

        result = extract_sheet_preview(path, max_rows=10)

        self.assertEqual(len(result["preview_rows"]), 10)

    def test_header_only_sheet_returns_empty_preview_rows(self):
        """헤더 행만 있고 데이터가 없는 빈 템플릿도 에러 없이 빈 리스트를 반환한다."""
        path = self._make([["회사명", "주소", "TEL", "FAX"]])

        result = extract_sheet_preview(path)

        self.assertEqual(result["headers"], ["회사명", "주소", "TEL", "FAX"])
        self.assertEqual(result["preview_rows"], [])


if __name__ == "__main__":
    unittest.main()
