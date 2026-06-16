from pathlib import Path

import pandas as pd


def parse_csv(file_path: str | Path) -> tuple[str, list[str]]:
    """
    Returns (text_representation, column_names).
    UTF-8 BOM 처리 포함 (Excel 내보내기 파일 대응).
    """
    path = Path(file_path)
    df = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
    df.fillna("", inplace=True)
    return df.to_string(index=False), df.columns.tolist()
