"""
문서 수정 앵커 해석 레이어 (PDF 우선 구현, 포맷 독립적 확장을 염두에 둠).

배경: patcher.py가 text_match anchor를 page.search_for(target_text)에 직접
의존해 해석해왔는데, 이 방식은 세 가지 문제가 반복됐다.

  1. search_for()는 PDF 내부 원시(그리기) 순서로만 매칭한다 — 읽기순서로
     재구성된 문자열(ax-engine parse_pdf, #30)로는 애초에 매치가 안 될 수 있다.
  2. 하나의 논리적 매치가 폰트 전환 등으로 여러 rect 조각으로 쪼개져 반환되면
     일부만 지워지는 결과가 나온다(#31).
  3. search_for() 반환 순서가 항상 좌→우가 아니어서(같은 줄의 여러 occurrence가
     오른쪽부터 그려진 경우 등), 조각을 인접 순서로만 비교하면 서로 먼 rect가
     하나로 잘못 묶이거나 occurrence 순서가 뒤바뀐다.

이 모듈은 "LLM은 무엇을 무엇으로 바꿀지와 문맥만 제공하고, 실제 위치 탐색·
후보 판정·실패 사유 결정은 BE가 결정적으로 처리한다"는 원칙 아래, anchor 해석을
patcher.py에서 분리한 별도 계층으로 둔다. 목표 구조:

    문서 원본 → (build_pdf_document_layout) → normalized token
              → (AnchorResolver.resolve) → ResolveResult
              → patcher.py가 RESOLVED만 렌더링에 사용

search_for() 자체를 없애는 것은 아니다 — token 기반 매칭이 실패했을 때 시도하는
fallback 전략(_search_for_fallback) 중 하나로 남겨둔다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


# ── 공용 타입 ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Token:
    """정규화된 텍스트 토큰 — 페이지 내 실제 읽기순서를 반영한다."""
    page: int                       # 0-based 페이지 인덱스
    text: str
    bbox: tuple[float, float, float, float]  # (x0, y0, x1, y1)
    line_id: int                    # 읽기순서 기준으로 계산한 줄 번호 (0부터)
    block_id: int                   # PyMuPDF가 보고한 원본 block 번호 (참고용)
    order_index: int                # 페이지 내 읽기순서 인덱스
    raw_order_index: int | None     # PDF 내부 원시 순서 인덱스 (가능하면 보존)
    source: str = "pdf"


class AnchorStatus:
    """ResolveResult.status에 사용하는 상태 값 (문자열 상수 — DB 저장값과는 별개)."""
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "not_found"
    UNSUPPORTED = "unsupported"


@dataclass
class ResolveResult:
    """AnchorResolver.resolve()의 반환 타입 — 실패를 None으로 뭉개지 않는다."""
    status: str
    page: int | None = None
    rect: object | None = None       # fitz.Rect (RESOLVED일 때만 값이 있음)
    matched_text: str = ""
    confidence: float = 0.0
    reason: str = ""
    candidates: list[dict] = field(default_factory=list)


@dataclass
class PdfDocumentLayout:
    """AnchorResolver가 참조하는 문서 레이아웃 — 페이지별 token 목록 + 원본 fitz.Document."""
    doc: object                      # fitz.Document (fallback 전략에서 search_for 호출용)
    pages: list[list[Token]]


# ── 1단계: PDF → normalized token ───────────────────────────────────────────

# 같은 줄로 묶을 Y좌표 허용 오차(pt) — ax-engine parsers/pdf_parser.py와 동일 기준
_LINE_Y_TOLERANCE = 3.0


def build_pdf_document_layout(doc) -> PdfDocumentLayout:
    """
    fitz.Document → PdfDocumentLayout.

    각 페이지의 word를 PDF 내부 그리기 순서가 아니라 Y좌표(줄) → X좌표 순으로
    재정렬해 실제 화면상 읽기순서를 반영하는 token 목록을 만든다. search_for()가
    도달하지 못하는 "읽기순서 문자열" 기반 매칭(AnchorResolver의 1차 전략)이
    이 token 목록을 사용한다.
    """
    pages: list[list[Token]] = []
    for page_idx, page in enumerate(doc):
        raw_words = page.get_text("words")  # (x0,y0,x1,y1,text,block_no,line_no,word_no)
        indexed = list(enumerate(raw_words))
        lines = _cluster_into_reading_order_lines(indexed)

        page_tokens: list[Token] = []
        order_index = 0
        for line_id, line_items in enumerate(lines):
            for raw_idx, w in line_items:
                page_tokens.append(Token(
                    page=page_idx,
                    text=w[4],
                    bbox=(w[0], w[1], w[2], w[3]),
                    line_id=line_id,
                    block_id=w[5],
                    order_index=order_index,
                    raw_order_index=raw_idx,
                    source="pdf",
                ))
                order_index += 1
        pages.append(page_tokens)
    return PdfDocumentLayout(doc=doc, pages=pages)


def _cluster_into_reading_order_lines(indexed_words: list[tuple[int, tuple]]) -> list[list[tuple[int, tuple]]]:
    """(raw_idx, word) 목록을 Y좌표로 줄을 묶고 각 줄 내부를 X좌표로 정렬한다."""
    if not indexed_words:
        return []

    sorted_by_y = sorted(indexed_words, key=lambda item: item[1][1])
    lines: list[list[tuple[int, tuple]]] = []
    for item in sorted_by_y:
        y0 = item[1][1]
        if lines and abs(y0 - lines[-1][0][1][1]) <= _LINE_Y_TOLERANCE:
            lines[-1].append(item)
        else:
            lines.append([item])

    for line in lines:
        line.sort(key=lambda item: item[1][0])  # x0
    return lines


# ── 2단계: token 목록 → 읽기순서 문자열 (매칭용 인덱스) ─────────────────────

def _build_reading_order_index(tokens: list[Token]) -> tuple[str, list[int]]:
    """
    tokens(이미 페이지 내 읽기순서)를 이어붙여 (문자열, 문자 인덱스→token 인덱스) 쌍을 만든다.

    같은 줄 안에서 토큰 사이 간격이 좁으면(폰트 크기 대비 작은 갭) 공백 없이 붙이고,
    넓으면 공백 하나를 넣는다 — ax-engine parsers/pdf_parser.py의 _join_words_by_gap과
    동일한 규칙이다(실제로 붙어 있는 텍스트가 별도 word로 쪼개지는 경우를 보정).
    줄이 바뀌면 개행을 넣는다. 구분 문자(공백·개행)는 어떤 token에도 속하지 않으므로
    -1로 표시한다.
    """
    chars: list[str] = []
    char_token_idx: list[int] = []
    prev: Token | None = None

    for i, tok in enumerate(tokens):
        if prev is not None:
            if tok.line_id != prev.line_id:
                chars.append("\n")
                char_token_idx.append(-1)
            else:
                gap = tok.bbox[0] - prev.bbox[2]
                threshold = (prev.bbox[3] - prev.bbox[1]) * 0.2
                if gap >= threshold:
                    chars.append(" ")
                    char_token_idx.append(-1)
        for ch in tok.text:
            chars.append(ch)
            char_token_idx.append(i)
        prev = tok

    return "".join(chars), char_token_idx


def _build_nospace_index(tokens: list[Token]) -> tuple[str, list[int]]:
    """모든 구분자를 제거한 버전 — 문서마다 공백 규칙이 달라 gap 기반 매칭이 실패할 때의 2차 시도."""
    text, char_token_idx = _build_reading_order_index(tokens)
    filtered_chars = []
    filtered_idx = []
    for ch, idx in zip(text, char_token_idx):
        if idx == -1:
            continue
        filtered_chars.append(ch)
        filtered_idx.append(idx)
    return "".join(filtered_chars), filtered_idx


def _union_token_rects(tokens: list[Token]):
    import fitz
    return fitz.Rect(
        min(t.bbox[0] for t in tokens),
        min(t.bbox[1] for t in tokens),
        max(t.bbox[2] for t in tokens),
        max(t.bbox[3] for t in tokens),
    )


def _search_in_indexed_string(
    page_idx: int, tokens: list[Token], text: str, char_token_idx: list[int],
    target: str, confidence: float,
) -> list[dict]:
    """text 안에서 target의 모든(비중첩) 위치를 찾아 후보 dict 목록으로 변환한다."""
    if not target:
        return []

    results: list[dict] = []
    start = 0
    while True:
        pos = text.find(target, start)
        if pos == -1:
            break
        span_token_idxs = sorted({
            char_token_idx[i] for i in range(pos, pos + len(target))
            if char_token_idx[i] != -1
        })
        if span_token_idxs:
            matched_tokens = [tokens[i] for i in span_token_idxs]
            results.append({
                "page": page_idx,
                "rect": _union_token_rects(matched_tokens),
                "matched_text": "".join(t.text for t in matched_tokens),
                "confidence": confidence,
            })
        start = pos + max(len(target), 1)
    return results


def _find_token_candidates(page_idx: int, tokens: list[Token], target: str) -> list[dict]:
    """페이지의 token 목록에서 target을 찾는다 — gap 기반 결합 우선, 실패 시 무공백 결합."""
    if not tokens:
        return []

    gapped_text, gapped_idx = _build_reading_order_index(tokens)
    candidates = _search_in_indexed_string(page_idx, tokens, gapped_text, gapped_idx, target, confidence=0.95)
    if candidates:
        return candidates

    nospace_text, nospace_idx = _build_nospace_index(tokens)
    nospace_target = re.sub(r"\s+", "", target)
    return _search_in_indexed_string(page_idx, tokens, nospace_text, nospace_idx, nospace_target, confidence=0.8)


# ── 3단계: fallback 전략 — search_for() 기반 (기존 PR #31 로직 이관) ────────

# 조각을 같은 occurrence로 묶을 때 허용할 최대 X간격 — 텍스트 높이의 배수.
# 실사용 문서에서 라벨(년/월) 사이 간격은 텍스트 높이의 ~1.1배였고, 표의
# 다른 셀에 있는 별개 발생은 ~20배였다 — 그 사이에서 넉넉히 잡는다.
_FRAGMENT_MERGE_GAP_RATIO = 4.0


def _group_search_rects_into_occurrences(rects: list) -> list:
    """
    search_for()가 반환한 rect 목록을 실제 발생(occurrence) 단위로 묶는다.

    다중 단어 검색어는 PDF 내부 span 경계(폰트 전환, 별도 시점에 겹쳐
    그려진 텍스트 등)에 따라 하나의 논리적 매치가 여러 rect로 쪼개져
    반환될 수 있다 — 이걸 첫 조각만 쓰면 일부만 지워지고 나머지는 새로
    그린 텍스트와 겹친다.

    주의: search_for()는 PDF 내부 그리기 순서로 rect를 반환하므로, 같은 줄의
    서로 다른 occurrence가 오른쪽→왼쪽 순서로 그려졌으면 반환 순서도 뒤집힌다.
    그 순서를 그대로 믿고 인접 rect끼리만 비교하면 gap이 음수가 되어(예:
    72 - 444 = -372) "간격이 좁다"는 조건을 항상 만족해버려, 실제로는 멀리
    떨어진 두 발생이 하나로 잘못 합쳐진다. 그룹핑 전에 반드시 Y→X 순으로
    재정렬해 gap 계산이 실제 시각적 인접성을 반영하게 한다(PR #31 blocking 이슈).
    """
    if not rects:
        return []

    sorted_rects = sorted(rects, key=lambda r: (r.y0, r.x0))

    groups: list[list] = [[sorted_rects[0]]]
    for r in sorted_rects[1:]:
        prev = groups[-1][-1]
        y_overlaps = not (r.y1 < prev.y0 or r.y0 > prev.y1)
        text_height = prev.y1 - prev.y0
        gap = r.x0 - prev.x1
        # 재정렬 후에도 혹시 남을 수 있는 음수 gap(겹치는 rect 등)은 안전하게 배제한다.
        close_enough = 0 <= gap < text_height * _FRAGMENT_MERGE_GAP_RATIO
        if y_overlaps and close_enough:
            groups[-1].append(r)
        else:
            groups.append([r])

    return [_union_rects(group) for group in groups]


def _union_rects(rects: list):
    import fitz
    return fitz.Rect(
        min(r.x0 for r in rects),
        min(r.y0 for r in rects),
        max(r.x1 for r in rects),
        max(r.y1 for r in rects),
    )


def _search_for_fallback(doc, target: str, pages_to_search: list[int]) -> list[dict]:
    """token 기반 매칭이 실패했을 때만 시도하는 2차 전략 — 기존 search_for() 경로."""
    results: list[dict] = []
    for page_idx in pages_to_search:
        page = doc[page_idx]
        rects = page.search_for(target)
        for r in _group_search_rects_into_occurrences(rects):
            results.append({"page": page_idx, "rect": r, "matched_text": target, "confidence": 0.6})
    return results


# ── 4단계: AnchorResolver ────────────────────────────────────────────────────

class AnchorResolver:
    """anchor dict + PdfDocumentLayout → ResolveResult."""

    def resolve(self, anchor: dict, layout: PdfDocumentLayout) -> ResolveResult:
        anchor_type = anchor.get("type", "")
        if anchor_type == "pdf_bbox":
            return self._resolve_pdf_bbox(anchor, layout)
        if anchor_type == "text_match":
            return self._resolve_text_match(anchor, layout)
        return ResolveResult(
            status=AnchorStatus.UNSUPPORTED,
            reason=f"지원하지 않는 anchor type: {anchor_type!r}",
        )

    def _resolve_pdf_bbox(self, anchor: dict, layout: PdfDocumentLayout) -> ResolveResult:
        import fitz

        page_num = anchor.get("page", 1)
        page_idx = page_num - 1
        if page_idx < 0 or page_idx >= len(layout.pages):
            return ResolveResult(status=AnchorStatus.NOT_FOUND, reason=f"페이지 범위 초과: page={page_num}")

        r = anchor.get("rect", {})
        if not r:
            return ResolveResult(status=AnchorStatus.NOT_FOUND, reason="anchor.rect 누락")
        try:
            rect = fitz.Rect(r["x0"], r["y0"], r["x1"], r["y1"])
        except (KeyError, TypeError):
            return ResolveResult(status=AnchorStatus.NOT_FOUND, reason=f"anchor.rect 형식 오류: {r!r}")

        return ResolveResult(
            status=AnchorStatus.RESOLVED, page=page_idx, rect=rect,
            matched_text="", confidence=1.0,
        )

    def _resolve_text_match(self, anchor: dict, layout: PdfDocumentLayout) -> ResolveResult:
        target = (anchor.get("target_text") or "").strip()
        if not target:
            return ResolveResult(status=AnchorStatus.NOT_FOUND, reason="anchor.target_text가 비어 있음")

        page_hint = anchor.get("page")
        if page_hint is not None:
            page_idx = int(page_hint) - 1
            pages_to_search = [page_idx] if 0 <= page_idx < len(layout.pages) else []
        else:
            pages_to_search = list(range(len(layout.pages)))

        candidates: list[dict] = []
        for page_idx in pages_to_search:
            candidates.extend(_find_token_candidates(page_idx, layout.pages[page_idx], target))

        if not candidates:
            candidates = _search_for_fallback(layout.doc, target, pages_to_search)

        if not candidates:
            return ResolveResult(
                status=AnchorStatus.NOT_FOUND,
                reason=f"'{target}' 위치를 찾지 못함 (token 매칭·search_for 모두 실패)",
            )

        requested = anchor.get("occurrence")
        if requested is None:
            if len(candidates) > 1:
                return ResolveResult(
                    status=AnchorStatus.AMBIGUOUS,
                    reason=f"'{target}'에 대해 {len(candidates)}개의 후보가 있어 occurrence 지정이 필요함",
                    candidates=candidates,
                )
            chosen = candidates[0]
        else:
            occurrence = max(1, int(requested))
            if occurrence > len(candidates):
                return ResolveResult(
                    status=AnchorStatus.NOT_FOUND,
                    reason=f"occurrence={occurrence}이지만 후보는 {len(candidates)}개뿐임",
                    candidates=candidates,
                )
            chosen = candidates[occurrence - 1]

        return ResolveResult(
            status=AnchorStatus.RESOLVED,
            page=chosen["page"],
            rect=chosen["rect"],
            matched_text=chosen["matched_text"],
            confidence=chosen["confidence"],
            candidates=candidates,
        )
