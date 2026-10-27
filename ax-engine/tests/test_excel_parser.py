import datetime
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import openpyxl

from parsers.excel_parser import extract_sheet_preview, parse_excel


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

    def test_datetime_cell_is_json_serializable(self):
        """
        [버그 수정] 날짜/시간 셀(openpyxl이 datetime으로 반환)이 그대로 나가면
        이 결과가 Django JSONField(UploadLog.result)에 저장될 때
        "Object of type datetime is not JSON serializable"로 죽는다
        (실제 xlsx 샘플의 거래일자 셀에서 재현됨). isoformat 문자열로
        변환해서 반환해야 한다.
        """
        path = self._make([
            ["날짜", "품목"],
            [datetime.datetime(2023, 8, 15, 0, 0), "사무용품A"],
        ])

        result = extract_sheet_preview(path)

        # json.dumps가 예외 없이 성공해야 실제 DB 저장 경로에서도 안전하다
        json.dumps(result)
        self.assertEqual(result["preview_rows"][0][0], "2023-08-15T00:00:00")

    def test_header_only_sheet_returns_empty_preview_rows(self):
        """헤더 행만 있고 데이터가 없는 빈 템플릿도 에러 없이 빈 리스트를 반환한다."""
        path = self._make([["회사명", "주소", "TEL", "FAX"]])

        result = extract_sheet_preview(path)

        self.assertEqual(result["headers"], ["회사명", "주소", "TEL", "FAX"])
        self.assertEqual(result["preview_rows"], [])


class TestParseExcelCellAddresses(unittest.TestCase):
    """
    [버그 수정] PatchPlan 생성 LLM이 anchor.cell을 실제 주소가 아니라
    "몇 번째 줄에 있었나"로 추측하다 보니, 인접한 라벨("문서번호"/"일자")을
    반복적으로 혼동해 매번 다른 칸을 가리키던 문제를 재현한다(실사용
    재현). 문서 텍스트에 실제 셀 주소(A1 표기)가 값과 함께 있어야
    LLM이 추측 없이 정확한 anchor를 만들 수 있다.
    """

    def setUp(self):
        self._tmp_files: list[str] = []

    def tearDown(self):
        for p in self._tmp_files:
            Path(p).unlink(missing_ok=True)

    def _make(self, rows: list[list]) -> str:
        path = _build_xlsx(rows)
        self._tmp_files.append(path)
        return path

    def test_document_text_includes_real_cell_addresses(self):
        """실사용 구조 재현: 문서번호(10행)와 일자(11행)가 연속된 라벨 행."""
        rows = [[]] * 9 + [["문서번호"], ["일자"]]
        path = self._make(rows)

        text, _sheet_names = parse_excel(path)

        # 같은 줄에 라벨과 주소가 함께 있어야 LLM이 "이 라벨=이 주소"를 알 수 있다
        self.assertIn("A10=문서번호", text)
        self.assertIn("A11=일자", text)

    def test_fully_blank_rows_are_skipped_to_keep_text_compact(self):
        """내용이 하나도 없는 행은 생략해 문서 텍스트가 불필요하게 길어지지 않게 한다."""
        rows = [[]] * 5 + [["값1"]]
        path = self._make(rows)

        text, _ = parse_excel(path)

        self.assertEqual(text.count("\n"), 1)  # "[시트: ...]" 줄 + 내용 1줄
        self.assertIn("A6=값1", text)

    def test_row_with_any_content_shows_adjacent_blank_cells_too(self):
        """
        [버그 수정] 라벨 옆의 값 칸이 비어 있으면 그 주소 자체가 텍스트에서
        아예 빠져, LLM이 "이 라벨 옆 빈 칸의 주소가 뭔지" 알 수 없어 채워야
        할 값의 anchor를 만들지 못하고 작업을 포기하는 문제가 실사용에서
        확인됐다(예: '일자' 라벨은 보이는데 그 옆 빈 값 칸 주소가 안 보여
        아예 변경을 안 만듦). 내용이 있는 행은 그 행의 빈 칸도 주소만
        노출해 "이 주소는 비어 있다"는 걸 LLM이 알 수 있게 한다.
        """
        rows = [["값1", None, None, "값4"]]
        path = self._make(rows)

        text, _ = parse_excel(path)

        self.assertIn("A1=값1", text)
        self.assertIn("D1=값4", text)
        self.assertIn("B1=", text)
        self.assertIn("C1=", text)

    def test_datetime_cell_is_json_safe_string_in_text(self):
        """날짜 셀도 isoformat 문자열로 안전하게 나온다."""
        rows = [[datetime.datetime(2023, 8, 15)]]
        path = self._make(rows)

        text, _ = parse_excel(path)

        self.assertIn("A1=2023-08-15T00:00:00", text)

    def test_sheet_names_returned(self):
        path = self._make([["a"]])

        _text, sheet_names = parse_excel(path)

        self.assertEqual(sheet_names, ["Sheet"])


if __name__ == "__main__":
    unittest.main()
