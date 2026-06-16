from pathlib import Path
from pypdf import PdfReader


def parse_pdf(file_path: str | Path) -> tuple[str, int]:
    """
    Returns (full_text, page_count).
    페이지별로 레이블을 붙여 LLM이 문서 위치를 참조할 수 있게 한다.
    """
    reader = PdfReader(str(file_path))

    pages: list[str] = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append(f"[페이지 {i}]\n{text.strip()}")

    return "\n\n".join(pages), len(reader.pages)
