import datetime
import openpyxl
from pathlib import Path


def _json_safe_cell(value):
    """
    openpyxl(data_only=True)이 셀 값으로 datetime/date/time을 그대로 돌려줄 수
    있는데, 이 값이 UploadLog.result(JSONField)에 저장될 때 psycopg2가 JSON
    직렬화를 시도하며 "Object of type datetime is not JSON serializable"로
    죽는다(실제 날짜 셀 있는 xlsx에서 재현됨). isoformat 문자열로 미리 바꿔둔다.
    """
    if value is None:
        return ""
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    return value


def _is_blank_cell(value) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def parse_excel(file_path: str | Path) -> tuple[str, list[str]]:
    """
    Returns (text_representation, sheet_names).

    각 값 옆에 실제 셀 주소(A1 표기)를 함께 담는다 — PatchPlan 생성 LLM이
    anchor.cell을 "몇 번째 줄에 있었나" 식으로 추측하면, 인접한 라벨(예:
    '문서번호'/'일자' 같은 연속된 행)을 반복적으로 혼동해 매번 다른 칸을
    가리키는 문제가 실사용에서 확인됐다. 주소를 텍스트에 직접 노출해
    추측 자체가 필요 없게 한다.

    내용이 하나도 없는 행은 통째로 생략해 텍스트 길이를 억제하지만,
    내용이 있는 행은 그 행의 빈 칸 주소도 함께 보여준다 — 라벨 옆의
    빈 값 칸 주소 자체가 안 보이면, LLM이 "이 라벨을 채우려면 어느
    칸에 써야 하는지" 알 수 없어 아예 작업을 포기하는 문제가 실사용에서
    확인됐다.
    """
    path = Path(file_path)
    wb = openpyxl.load_workbook(path, data_only=True)
    try:
        chunks: list[str] = []
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            lines: list[str] = []
            for row in ws.iter_rows():
                if all(_is_blank_cell(cell.value) for cell in row):
                    continue
                cells = [
                    f"{cell.coordinate}={'' if _is_blank_cell(cell.value) else _json_safe_cell(cell.value)}"
                    for cell in row
                ]
                lines.append(" | ".join(cells))
            chunks.append(f"[시트: {sheet_name}]\n" + "\n".join(lines))

        return "\n\n".join(chunks), wb.sheetnames
    finally:
        wb.close()


def extract_sheet_preview(file_path: str | Path, max_rows: int = 50) -> dict:
    """
    첫 번째 시트의 1행을 헤더로, 이후 행을 미리보기 데이터로 추출한다.
    프론트엔드 "시트 미리보기" 표(ExcelViewer)에 그대로 넣을 수 있는 형태다.

    패치 적용 전(artifact 없는) 최초 분석 단계에서도 실제 시트 내용을 보여주기
    위한 용도다 — 응답 크기 제한을 위해 데이터 행은 max_rows까지만 담는다.

    Returns: {"headers": [str, ...], "preview_rows": [[cell, ...], ...]}
    """
    path = Path(file_path)
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        ws = wb[wb.sheetnames[0]]
        rows_iter = ws.iter_rows(values_only=True)

        first_row = next(rows_iter, None) or ()
        headers = [str(_json_safe_cell(v)) for v in first_row]

        preview_rows: list[list] = []
        for row in rows_iter:
            if len(preview_rows) >= max_rows:
                break
            preview_rows.append([_json_safe_cell(v) for v in row])

        return {"headers": headers, "preview_rows": preview_rows}
    finally:
        wb.close()
