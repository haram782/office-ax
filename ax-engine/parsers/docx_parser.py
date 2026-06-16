from pathlib import Path


def parse_docx(file_path: str | Path) -> tuple[str, dict]:
    """
    Returns (text_content, meta).
    단락 텍스트 + 표 셀 내용을 모두 추출한다.
    """
    try:
        from docx import Document
    except ImportError:
        return "[DOCX_UNAVAILABLE: pip install python-docx]", {}

    doc = Document(str(file_path))
    sections: list[str] = []

    # 단락
    paras = [p.text for p in doc.paragraphs if p.text.strip()]
    if paras:
        sections.append("\n".join(paras))

    # 표
    for i, table in enumerate(doc.tables, 1):
        rows = []
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            rows.append(" | ".join(cells))
        sections.append(f"[표 {i}]\n" + "\n".join(rows))

    return "\n\n".join(sections) or "[빈 문서]", {
        "paragraphs": len(doc.paragraphs),
        "tables":     len(doc.tables),
    }
