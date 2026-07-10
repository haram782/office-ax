from pathlib import Path

import fitz

# 같은 줄로 묶을 Y좌표 허용 오차(pt) — 폰트 크기·베이스라인 미세 차이를 흡수한다
_LINE_Y_TOLERANCE = 3.0


def _words_to_reading_order_text(words: list[tuple]) -> str:
    """
    PyMuPDF get_text("words") 결과(그리기 순서)를 실제 화면에 보이는
    좌→우, 위→아래 읽는 순서로 재구성한다.

    일부 PDF(빈칸에 값을 나중에 채워 넣는 방식으로 만들어진 관공서·기업
    양식 등)는 라벨과 채워진 값을 서로 다른 시점에 그려서, 그리기 순서가
    실제 읽는 순서와 어긋난다 — 예: "년 월 일"을 먼저 그리고 "2026 6 27"을
    나중에 겹쳐 그리면, 기본 추출은 "년월일2026627" 순으로 나온다.
    Y좌표로 줄을 묶고 각 줄 내부를 X좌표로 정렬하면 실제 읽는 순서
    ("2026년6월27일")가 복원된다.
    """
    if not words:
        return ""

    # word: (x0, y0, x1, y1, text, block_no, line_no, word_no)
    sorted_by_y = sorted(words, key=lambda w: w[1])

    lines: list[list[tuple]] = []
    for word in sorted_by_y:
        if lines and abs(word[1] - lines[-1][0][1]) <= _LINE_Y_TOLERANCE:
            lines[-1].append(word)
        else:
            lines.append([word])

    line_texts = []
    for line in lines:
        line.sort(key=lambda w: w[0])
        line_texts.append(_join_words_by_gap(line))

    return "\n".join(line_texts)


def _join_words_by_gap(line_words: list[tuple]) -> str:
    """
    같은 줄의 단어들을 X좌표 간격 기준으로 이어붙인다.

    PyMuPDF의 "words"는 공백으로 토큰을 나누는데, 일부 폰트(예: 한글
    폰트로 그린 숫자·문장부호)는 글자 사이에 렌더링 간격이 생겨 실제로는
    붙어 있는 텍스트("1,000,000원")가 여러 "단어"로 쪼개진다. 단어 사이
    간격이 좁으면(폰트 크기 대비 작은 갭) 공백 없이 붙이고, 넓으면 실제
    단어 경계로 보고 공백을 넣는다.
    """
    parts = [line_words[0][4]]
    for prev, cur in zip(line_words, line_words[1:]):
        gap = cur[0] - prev[2]
        # 갭 임계값을 텍스트 높이에 비례시켜 폰트 크기 변화에 대응한다
        threshold = (prev[3] - prev[1]) * 0.2
        parts.append("" if gap < threshold else " ")
        parts.append(cur[4])
    return "".join(parts)


def parse_pdf(file_path: str | Path) -> tuple[str, int]:
    """
    Returns (full_text, page_count).
    페이지별로 레이블을 붙여 LLM이 문서 위치를 참조할 수 있게 한다.

    단순 get_text()가 아니라 단어 단위 좌표로 읽는 순서를 재구성한다
    (이유는 _words_to_reading_order_text 참조).
    """
    doc = fitz.open(str(file_path))
    try:
        pages: list[str] = []
        for i, page in enumerate(doc, start=1):
            words = page.get_text("words")
            text = _words_to_reading_order_text(words)
            pages.append(f"[페이지 {i}]\n{text.strip()}")

        return "\n\n".join(pages), len(doc)
    finally:
        doc.close()
