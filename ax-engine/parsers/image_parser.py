"""이미지 파일(PNG/JPG/JPEG/WEBP/GIF) → OCR 텍스트 추출."""
from pathlib import Path

from parsers.ocr_parser import ocr_extract


def parse_image(file_path: str | Path) -> tuple[str, dict]:
    """
    Returns (ocr_text, meta).
    ocr_parser의 이미지 로딩 경로를 재사용한다.
    """
    path = Path(file_path)
    text, meta = ocr_extract(path)
    meta["format"] = path.suffix.lower().lstrip(".")
    return text or "[이미지에서 텍스트를 추출할 수 없습니다]", meta
