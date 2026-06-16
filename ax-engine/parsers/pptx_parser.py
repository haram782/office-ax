from pathlib import Path


def parse_pptx(file_path: str | Path) -> tuple[str, dict]:
    """
    Returns (text_for_llm, meta).

    meta["structured"] — AI 패치 엔진이 셰이프를 특정할 때 사용하는 트리:
      [
        {
          "index": 0,          # 0-based 슬라이드 인덱스
          "title": "...",      # 제목 셰이프 텍스트 (첫 줄)
          "shapes": [          # 텍스트 셰이프 목록
            {"index": 0, "name": "Title 1", "text": "..."}
          ],
          "tables": [          # 표 목록
            {
              "shape_index": 2,
              "shape_name": "표 1",
              "rows": [["셀A", "셀B"], ...]
            }
          ]
        }, ...
      ]
    """
    try:
        from pptx import Presentation
    except ImportError:
        return "[PPTX_UNAVAILABLE: pip install python-pptx]", {}

    prs = Presentation(str(file_path))
    slides_text: list[str] = []
    structured: list[dict] = []

    for slide_idx, slide in enumerate(prs.slides):
        slide_num = slide_idx + 1
        slide_data: dict = {
            "index":  slide_idx,
            "title":  "",
            "shapes": [],
            "tables": [],
        }
        texts: list[str] = []

        for shape_idx, shape in enumerate(slide.shapes):
            if shape.has_text_frame:
                text = shape.text_frame.text.strip()
                if text:
                    texts.append(text)
                    slide_data["shapes"].append({
                        "index": shape_idx,
                        "name":  shape.name,
                        "text":  text,
                    })
                    # 제목 셰이프 우선순위: 이름에 title/제목 포함, 또는 첫 번째 텍스트
                    if not slide_data["title"] and (
                        "title" in shape.name.lower()
                        or "제목" in shape.name
                        or not slide_data["shapes"][:-1]  # 첫 번째 텍스트 셰이프
                    ):
                        slide_data["title"] = text.split("\n")[0]

            if shape.has_table:
                table_rows: list[list[str]] = []
                for row in shape.table.rows:
                    row_cells = [cell.text.strip() for cell in row.cells]
                    table_rows.append(row_cells)
                    row_str = " | ".join(row_cells)
                    if row_str.strip():
                        texts.append(row_str)
                slide_data["tables"].append({
                    "shape_index": shape_idx,
                    "shape_name":  shape.name,
                    "rows":        table_rows,
                })

        if slide.has_notes_slide:
            note = slide.notes_slide.notes_text_frame.text.strip()
            if note:
                texts.append(f"[노트] {note}")

        if texts:
            slides_text.append(f"[슬라이드 {slide_num}]\n" + "\n".join(texts))
        structured.append(slide_data)

    text_content = "\n\n".join(slides_text) or "[빈 프레젠테이션]"
    meta = {
        "slides":     len(prs.slides),
        "structured": structured,
    }
    return text_content, meta
