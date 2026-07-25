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
    find_adjacent_table_cell_rect,
    resolve_pdf_fill_anchor,
    resolve_pdf_preview_anchor,
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


class ResolvePdfPreviewAnchorTest(unittest.TestCase):
    """
    resolve_pdf_preview_anchor — PatchPlan 생성 시점에 text_match anchor를
    미리 해석해 프론트엔드 하이라이트(page/rect)로 쓸 수 있는 dict를 만든다.

    PDF는 anchor.type이 항상 text_match라 프론트가 하이라이트를 그릴 좌표가
    없었다(pdf_bbox 전용인 PdfPageCanvas가 아예 아무것도 못 그림 — 실사용
    재현). 이 함수가 그 변환을 담당한다.
    """

    def test_resolved_match_returns_1_based_page_and_rect_dict(self):
        """
        [버그 수정] AnchorResolver의 page는 0-based인데 프론트(PDF.js)는
        1-based 페이지 번호를 쓴다 — 그대로 넘기면 페이지가 하나씩 밀린다.
        """
        pdf_bytes = _build_pdf_simple("Hello World")

        result = resolve_pdf_preview_anchor(
            pdf_bytes, {"type": "text_match", "target_text": "World", "occurrence": 1},
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["page"], 1, "단일 페이지 문서는 1-based로 1이어야 한다")
        rect = result["rect"]
        self.assertLess(rect["x0"], rect["x1"])
        self.assertLess(rect["y0"], rect["y1"])

    def test_ambiguous_match_returns_none(self):
        """후보가 여러 개라 위치를 특정 못 하면(AMBIGUOUS) 잘못 추측해 표시하지 않고 None."""
        pdf_bytes = _build_pdf_two_occurrences(left_first=True)

        result = resolve_pdf_preview_anchor(
            pdf_bytes, {"type": "text_match", "target_text": "개인정보"},
        )

        self.assertIsNone(result)

    def test_not_found_returns_none(self):
        pdf_bytes = _build_pdf_simple("Hello World")

        result = resolve_pdf_preview_anchor(
            pdf_bytes, {"type": "text_match", "target_text": "존재하지 않는 문구"},
        )

        self.assertIsNone(result)

    def test_corrupt_pdf_bytes_returns_none_without_raising(self):
        """손상된 파일 등 인프라성 실패는 예외를 전파하지 않고 None으로 격리한다."""
        result = resolve_pdf_preview_anchor(
            b"not a real pdf", {"type": "text_match", "target_text": "World"},
        )

        self.assertIsNone(result)


def _build_pdf_with_table(label: str, rows: int = 1, cols: int = 2, label_col: int = 0) -> bytes:
    """
    실제 선(line)으로 그린 표 안에 label을 넣은 PDF. PyMuPDF의 find_tables()가
    실제로 감지할 수 있는 표 구조를 만든다(테스트 대상 함수가 이 감지 결과에
    의존하므로, 감지 가능한 진짜 표가 있어야 의미 있는 테스트가 된다).
    """
    import fitz
    import io

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    x0, y0 = 100, 100
    col_w, row_h = 120, 40
    x1 = x0 + col_w * cols
    y1 = y0 + row_h * rows

    for r in range(rows + 1):
        y = y0 + r * row_h
        page.draw_line((x0, y), (x1, y))
    for c in range(cols + 1):
        x = x0 + c * col_w
        page.draw_line((x, y0), (x, y1))

    label_x = x0 + label_col * col_w + 10
    label_y = y0 + row_h // 2 + 4
    page.insert_text((label_x, label_y), label, fontsize=11, fontname="korea-s")

    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


class FindAdjacentTableCellRectTest(unittest.TestCase):
    """
    find_adjacent_table_cell_rect — "라벨 뒤에 값을 채워라"(change.original == "")
    요청에서 redact_overlay가 라벨 자신의 rect를 덮어써 라벨이 사라지는 문제
    (실사용 재현)를 막기 위해, 실제로 감지된 표 구조에서 라벨 옆(같은 행,
    다음 열) 칸의 실제 bbox를 찾는다 — "빈 공간이 이 정도일 것"이라는 추측이
    아니라 문서에 실제로 그려진 표 경계를 근거로 삼는다.
    """

    def test_returns_next_column_cell_in_same_row(self):
        import fitz
        pdf_bytes = _build_pdf_with_table("라벨", rows=1, cols=2, label_col=0)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        layout = build_pdf_document_layout(doc)
        label_result = AnchorResolver().resolve(
            {"type": "text_match", "target_text": "라벨", "occurrence": 1}, layout,
        )
        self.assertEqual(label_result.status, AnchorStatus.RESOLVED)

        adjacent = find_adjacent_table_cell_rect(doc, label_result.page, label_result.rect)
        doc.close()

        self.assertIsNotNone(adjacent)
        # 표는 x=100~340, 열 너비 120 — 라벨이 0열(100~220)이므로 인접 칸은 1열(220~340)
        self.assertAlmostEqual(adjacent.x0, 220, delta=1)
        self.assertAlmostEqual(adjacent.x1, 340, delta=1)

    def test_returns_none_when_label_is_in_last_column(self):
        import fitz
        pdf_bytes = _build_pdf_with_table("라벨", rows=1, cols=2, label_col=1)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        layout = build_pdf_document_layout(doc)
        label_result = AnchorResolver().resolve(
            {"type": "text_match", "target_text": "라벨", "occurrence": 1}, layout,
        )

        adjacent = find_adjacent_table_cell_rect(doc, label_result.page, label_result.rect)
        doc.close()

        self.assertIsNone(adjacent, "마지막 열이라 다음 칸이 없으므로 None이어야 한다")

    def test_returns_none_when_no_table_detected(self):
        """표 없이 그냥 텍스트만 있으면(find_tables가 아무것도 못 찾음) None."""
        import fitz
        # 표(선) 없이 순수 텍스트만 있는 PDF — 라벨 자체는 라틴 문자라
        # 기본(helv) 폰트로도 검색 가능하다(한글 폰트 이슈와 무관하게 격리).
        pdf_bytes = _build_pdf_simple("Label")
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        layout = build_pdf_document_layout(doc)
        label_result = AnchorResolver().resolve(
            {"type": "text_match", "target_text": "Label", "occurrence": 1}, layout,
        )
        self.assertEqual(label_result.status, AnchorStatus.RESOLVED)

        adjacent = find_adjacent_table_cell_rect(doc, label_result.page, label_result.rect)
        doc.close()

        self.assertIsNone(adjacent)


class ResolvePdfFillAnchorTest(unittest.TestCase):
    """
    resolve_pdf_fill_anchor — is_blank_fill(change.original == "")일 때만
    AnchorResolver의 결과 rect를 표의 인접 칸으로 바꿔치기한다. 기존 "이
    텍스트 자체를 교체"하는 경우(원본값이 있는 경우)는 라벨 자신의 rect를
    그대로 써야 하므로 건드리지 않는다.
    """

    def test_blank_fill_shifts_rect_to_adjacent_cell(self):
        import fitz
        pdf_bytes = _build_pdf_with_table("라벨", rows=1, cols=2, label_col=0)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        layout = build_pdf_document_layout(doc)

        result = resolve_pdf_fill_anchor(
            layout, {"type": "text_match", "target_text": "라벨", "occurrence": 1},
            is_blank_fill=True,
        )
        doc.close()

        self.assertEqual(result.status, AnchorStatus.RESOLVED)
        self.assertAlmostEqual(result.rect.x0, 220, delta=1, msg="라벨이 아니라 인접 칸을 가리켜야 한다")

    def test_non_blank_fill_keeps_label_rect(self):
        """원본값이 있는 교체 요청은 라벨(target_text) 자신의 rect를 그대로 유지한다."""
        import fitz
        pdf_bytes = _build_pdf_with_table("라벨", rows=1, cols=2, label_col=0)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        layout = build_pdf_document_layout(doc)

        result = resolve_pdf_fill_anchor(
            layout, {"type": "text_match", "target_text": "라벨", "occurrence": 1},
            is_blank_fill=False,
        )
        doc.close()

        self.assertEqual(result.status, AnchorStatus.RESOLVED)
        # 라벨 텍스트는 셀 왼쪽 경계(100)가 아니라 실제로 그려진 위치(110, 셀 안쪽 여백)에서
        # 시작한다 — 인접 칸(220)으로 바뀌지 않고 라벨 자신의 위치를 유지하는지가 핵심이다.
        self.assertAlmostEqual(result.rect.x0, 110, delta=3, msg="교체 요청은 라벨 자신의 rect를 유지해야 한다")

    def test_ambiguous_result_unaffected_by_blank_fill_flag(self):
        import fitz
        pdf_bytes = _build_pdf_two_occurrences(left_first=True)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        layout = build_pdf_document_layout(doc)

        result = resolve_pdf_fill_anchor(
            layout, {"type": "text_match", "target_text": "개인정보"}, is_blank_fill=True,
        )
        doc.close()

        self.assertEqual(result.status, AnchorStatus.AMBIGUOUS)


if __name__ == "__main__":
    unittest.main()
