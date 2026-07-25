import openpyxl
import pandas as pd
from pathlib import Path


def parse_excel(file_path: str | Path) -> tuple[str, list[str]]:
    """
    Returns (text_representation, sheet_names).
    dtype=str로 읽어 숫자 포맷 변환 없이 원본 셀 값을 보존한다.
    """
    path = Path(file_path)
    xl = pd.ExcelFile(path, engine="openpyxl")

    chunks: list[str] = []
    for sheet in xl.sheet_names:
        df = pd.read_excel(xl, sheet_name=sheet, dtype=str)
        df.fillna("", inplace=True)
        chunks.append(f"[시트: {sheet}]\n{df.to_string(index=False)}")

    return "\n\n".join(chunks), xl.sheet_names


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
        headers = ["" if v is None else str(v) for v in first_row]

        preview_rows: list[list] = []
        for row in rows_iter:
            if len(preview_rows) >= max_rows:
                break
            preview_rows.append(["" if v is None else v for v in row])

        return {"headers": headers, "preview_rows": preview_rows}
    finally:
        wb.close()
