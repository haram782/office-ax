import hashlib
import tempfile

import pandas as pd


def save_temp_file(uploaded_file, suffix: str) -> str:
    """업로드/스트림 객체를 임시 파일로 저장 후 경로 반환."""
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        for chunk in uploaded_file.chunks():
            tmp.write(chunk)
    finally:
        tmp.close()
    return tmp.name


def compute_sha256(file_path: str) -> str:
    """파일 내용의 SHA-256 해시값 반환. 중복 업로드 감지용."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def extract_excel_columns(file_path: str) -> list[str]:
    """파일 구조 해시 계산용. nrows=0으로 헤더만 읽어 파싱 비용 최소화."""
    xl = pd.ExcelFile(file_path, engine="openpyxl")
    cols: list[str] = []
    for sheet in xl.sheet_names:
        df = pd.read_excel(xl, sheet_name=sheet, nrows=0, dtype=str)
        cols.extend(df.columns.tolist())
    return cols


def extract_csv_columns(file_path: str) -> list[str]:
    """CSV 헤더 행만 읽어 컬럼명 반환. UTF-8 BOM 처리 포함."""
    df = pd.read_csv(file_path, nrows=0, dtype=str, encoding="utf-8-sig")
    return df.columns.tolist()


def generic_structure_hash(suffix: str, filename: str) -> str:
    """
    비정형 포맷(DOCX/PPTX/HWP/이미지)용 구조 해시.
    날짜·번호 토큰을 제거한 파일명 골격 + 확장자로 fingerprint 생성.
    """
    import re
    stem = re.sub(r"[\d\-_]+", "_", filename)
    raw = f"{suffix}::{stem}".encode()
    return hashlib.md5(raw).hexdigest()
