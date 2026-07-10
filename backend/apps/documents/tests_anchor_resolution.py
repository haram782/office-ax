"""
anchor_resolution.py (AnchorResolver / token 레이어) 단위 테스트.

DB를 쓰지 않는 순수 로직이므로 unittest.TestCase를 쓴다
(tests_patcher_pure.py와 동일한 관례).
"""
import unittest

from apps.documents.anchor_resolution import (
    AnchorResolver,
    AnchorStatus,
    Token,
    _group_search_rects_into_occurrences,
    build_pdf_document_layout,
)


def _build_pdf_two_occurrences(left_first: bool) -> bytes:
    """
    같은 Y좌표에 "개인정보"를 두 번 그린 PDF.

    left_first=True: 왼쪽(x=72)을 먼저, 오른쪽(x=400)을 나중에 그린다(정상 순서).
    left_first=False: 오른쪽을 먼저, 왼쪽을 나중에 그린다 — search_for()가
    [(400,444), (72,116)] 순서(그리기 순서)로 rect를 반환하게 만드는 재현 케이스
    (PR #31 blocking 이슈: 이 순서를 그대로 믿고 인접 비교하면 gap이 음수가 되어
    멀리 떨어진 두 발생이 하나로 합쳐진다).
    """
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    positions = [72, 400] if left_first else [400, 72]
    for x in positions:
        page.insert_text((x, 300), "개인정보", fontsize=11, fontname="korea-s", color=(0, 0, 0))
    import io
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def _build_pdf_fragmented_field() -> bytes:
    """라벨("년 월 일")과 값("2026 6 27")을 별도 시점에 겹쳐 그린 빈칸 채움형 PDF."""
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((235, 715), "년", fontsize=11, fontname="korea-s", color=(0, 0, 0))
    page.insert_text((295, 715), "월", fontsize=11, fontname="korea-s", color=(0, 0, 0))
    page.insert_text((345, 715), "일", fontsize=11, fontname="korea-s", color=(0, 0, 0))
    page.insert_text((190, 715), "2026", fontsize=11, fontname="helv", color=(0, 0, 0))
    page.insert_text((265, 715), "6", fontsize=11, fontname="helv", color=(0, 0, 0))
    page.insert_text((315, 715), "27", fontsize=11, fontname="helv", color=(0, 0, 0))
    import io
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def _build_pdf_simple(text: str) -> bytes:
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 100), text, fontsize=12, color=(0, 0, 0))
    import io
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


class GroupSearchRectsOrderingTest(unittest.TestCase):
    """_group_search_rects_into_occurrences가 search_for() 반환 순서에 안전한지 검증."""

    def test_left_to_right_order_keeps_occurrences_separate(self):
        import fitz
        rects = [fitz.Rect(72, 300, 116, 311), fitz.Rect(400, 300, 444, 311)]
        groups = _group_search_rects_into_occurrences(rects)
        self.assertEqual(len(groups), 2)
        self.assertLess(groups[0].x0, groups[1].x0, "occurrence 1은 시각적으로 왼쪽 rect여야 한다")

    def test_right_to_left_order_still_separates_and_sorts_left_first(self):
        """
        [버그 재현] search_for()가 오른쪽 rect를 먼저 반환해도(그리기 순서),
        결과 그룹은 여전히 분리돼야 하고 occurrence 1은 왼쪽 rect여야 한다.

        수정 전: gap = r.x0 - prev.x1 = 72 - 444 = -372 < text_height*4 → True로
        판정돼 두 rect가 하나의 넓은 rect로 잘못 합쳐졌다.
        """
        import fitz
        rects = [fitz.Rect(400, 300, 444, 311), fitz.Rect(72, 300, 116, 311)]
        groups = _group_search_rects_into_occurrences(rects)
        self.assertEqual(
            len(groups), 2,
            "그리기 순서가 오른쪽→왼쪽이어도 두 발생은 합쳐지지 않고 분리돼야 한다",
        )
        self.assertLess(
            groups[0].x0, groups[1].x0,
            "그리기 순서와 무관하게 occurrence 1은 시각적으로 왼쪽 rect여야 한다",
        )


class BuildPdfDocumentLayoutTest(unittest.TestCase):
    def test_tokens_are_in_visual_reading_order_regardless_of_draw_order(self):
        """
        라벨/값이 별도 시점에 겹쳐 그려진 문서에서도, token은 PDF 원시(그리기) 순서가
        아니라 실제 화면상 좌→우 읽기순서로 정렬돼야 한다.
        """
        import fitz
        doc = fitz.open(stream=_build_pdf_fragmented_field(), filetype="pdf")
        layout = build_pdf_document_layout(doc)
        doc.close()

        self.assertEqual(len(layout.pages), 1)
        texts = [t.text for t in layout.pages[0]]
        self.assertEqual(
            texts, ["2026", "년", "6", "월", "27", "일"],
            f"읽기순서로 재구성된 token 시퀀스가 예상과 다르다: {texts}",
        )

    def test_tokens_carry_bbox_and_line_id(self):
        import fitz
        doc = fitz.open(stream=_build_pdf_simple("Hello World"), filetype="pdf")
        layout = build_pdf_document_layout(doc)
        doc.close()

        tokens = layout.pages[0]
        self.assertTrue(len(tokens) >= 2)
        for tok in tokens:
            self.assertIsInstance(tok, Token)
            self.assertEqual(tok.source, "pdf")
            self.assertEqual(len(tok.bbox), 4)
            self.assertEqual(tok.line_id, 0)


class AnchorResolverPdfBboxTest(unittest.TestCase):
    def test_pdf_bbox_resolves_directly_with_full_confidence(self):
        import fitz
        doc = fitz.open(stream=_build_pdf_simple("Hello"), filetype="pdf")
        layout = build_pdf_document_layout(doc)

        result = AnchorResolver().resolve(
            {"type": "pdf_bbox", "page": 1, "rect": {"x0": 10, "y0": 10, "x1": 50, "y1": 30}},
            layout,
        )
        doc.close()

        self.assertEqual(result.status, AnchorStatus.RESOLVED)
        self.assertEqual(result.page, 0)
        self.assertEqual(result.confidence, 1.0)

    def test_unknown_anchor_type_is_unsupported(self):
        import fitz
        doc = fitz.open(stream=_build_pdf_simple("Hello"), filetype="pdf")
        layout = build_pdf_document_layout(doc)

        result = AnchorResolver().resolve({"type": "table_cell", "row": 1}, layout)
        doc.close()

        self.assertEqual(result.status, AnchorStatus.UNSUPPORTED)
        self.assertTrue(result.reason)


class AnchorResolverTextMatchTest(unittest.TestCase):
    def test_simple_text_match_resolves_via_tokens(self):
        """단일 페이지 짧은 텍스트 교체 happy path."""
        import fitz
        doc = fitz.open(stream=_build_pdf_simple("Hello World"), filetype="pdf")
        layout = build_pdf_document_layout(doc)

        result = AnchorResolver().resolve(
            {"type": "text_match", "occurrence": 1, "target_text": "World"}, layout,
        )
        doc.close()

        self.assertEqual(result.status, AnchorStatus.RESOLVED)
        self.assertEqual(result.page, 0)
        self.assertIsNotNone(result.rect)

    def test_fragmented_field_resolves_full_span(self):
        """PR #31 회귀 — 여러 조각으로 쪼개지는 target_text도 전체 span으로 해석돼야 한다."""
        import fitz
        doc = fitz.open(stream=_build_pdf_fragmented_field(), filetype="pdf")
        layout = build_pdf_document_layout(doc)

        result = AnchorResolver().resolve(
            {"type": "text_match", "occurrence": 1, "target_text": "2026 6 27"}, layout,
        )
        doc.close()

        self.assertEqual(result.status, AnchorStatus.RESOLVED)
        # target_text("2026 6 27")는 읽기순서 문자열엔 그대로 없어(라벨과 섞여
        # "2026 년 6 월 27 일"이 됨) fallback(search_for 기반) 전략으로 해석된다.
        # "2026"만 좁게 잡던 옛 버그라면 rect 폭이 "27"의 시작(x0=315)에 못 미친다.
        self.assertGreater(result.rect.x1, 320, f"matched_text={result.matched_text!r}")

    def test_reading_order_phrase_not_found_by_search_for_but_found_by_tokens(self):
        """
        [핵심] search_for(전체 구문)은 실패하지만(원시 순서 불일치),
        token 기반 읽기순서 재구성으로는 후보를 찾을 수 있어야 한다.

        PR #30(ax-engine 읽기순서 재구성) 덕분에 LLM은 이제 "2026년 6월 27일"처럼
        조사가 포함된 완전한 구문을 target_text로 생성할 수 있는데, search_for()는
        PDF 내부 원시 순서로만 매칭해 이 구문으로는 0 rects를 반환한다 — 그러나
        읽기순서로 재구성된 token 문자열에서는 이 구문이 그대로 나타난다.
        """
        import fitz
        doc = fitz.open(stream=_build_pdf_fragmented_field(), filetype="pdf")

        # search_for()가 원시 순서 기반이라 완전한 구문은 못 찾는다는 전제 확인
        raw_hits = doc[0].search_for("2026년6월27일")
        self.assertEqual(raw_hits, [], "이 전제가 깨지면 테스트 픽스처를 재검토해야 한다")

        layout = build_pdf_document_layout(doc)
        result = AnchorResolver().resolve(
            {"type": "text_match", "occurrence": 1, "target_text": "2026년6월27일"}, layout,
        )
        doc.close()

        self.assertEqual(
            result.status, AnchorStatus.RESOLVED,
            f"token 기반 매칭도 실패함: {result.reason}",
        )

    def test_multiple_candidates_without_occurrence_is_ambiguous(self):
        """occurrence 지정 없이 후보가 여러 개면 자동 반영하지 말고 AMBIGUOUS로 멈춰야 한다."""
        import fitz
        doc = fitz.open(stream=_build_pdf_two_occurrences(left_first=True), filetype="pdf")
        layout = build_pdf_document_layout(doc)

        result = AnchorResolver().resolve(
            {"type": "text_match", "target_text": "개인정보"}, layout,
        )
        doc.close()

        self.assertEqual(result.status, AnchorStatus.AMBIGUOUS)
        self.assertEqual(len(result.candidates), 2)

    def test_same_line_left_drawn_first_separates_occurrences(self):
        import fitz
        doc = fitz.open(stream=_build_pdf_two_occurrences(left_first=True), filetype="pdf")
        layout = build_pdf_document_layout(doc)
        resolver = AnchorResolver()

        r1 = resolver.resolve({"type": "text_match", "occurrence": 1, "target_text": "개인정보"}, layout)
        r2 = resolver.resolve({"type": "text_match", "occurrence": 2, "target_text": "개인정보"}, layout)
        doc.close()

        self.assertEqual(r1.status, AnchorStatus.RESOLVED)
        self.assertEqual(r2.status, AnchorStatus.RESOLVED)
        self.assertLess(r1.rect.x0, r2.rect.x0, "occurrence 1은 왼쪽, occurrence 2는 오른쪽이어야 한다")

    def test_same_line_right_drawn_first_still_resolves_left_to_right(self):
        """[버그 재현] 그리기 순서가 오른쪽→왼쪽이어도 occurrence는 시각적 순서를 따라야 한다."""
        import fitz
        doc = fitz.open(stream=_build_pdf_two_occurrences(left_first=False), filetype="pdf")
        layout = build_pdf_document_layout(doc)
        resolver = AnchorResolver()

        r1 = resolver.resolve({"type": "text_match", "occurrence": 1, "target_text": "개인정보"}, layout)
        r2 = resolver.resolve({"type": "text_match", "occurrence": 2, "target_text": "개인정보"}, layout)
        doc.close()

        self.assertEqual(r1.status, AnchorStatus.RESOLVED)
        self.assertEqual(r2.status, AnchorStatus.RESOLVED)
        self.assertLess(
            r1.rect.x0, r2.rect.x0,
            "그리기 순서가 뒤바뀌어도 occurrence 1은 시각적으로 왼쪽이어야 한다",
        )

    def test_not_found_returns_structured_reason(self):
        import fitz
        doc = fitz.open(stream=_build_pdf_simple("Hello World"), filetype="pdf")
        layout = build_pdf_document_layout(doc)

        result = AnchorResolver().resolve(
            {"type": "text_match", "target_text": "존재하지 않는 문구"}, layout,
        )
        doc.close()

        self.assertEqual(result.status, AnchorStatus.NOT_FOUND)
        self.assertTrue(result.reason)


if __name__ == "__main__":
    unittest.main()
