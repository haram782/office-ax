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
