"""
parse_pdf() 텍스트 추출 순서 테스트.

버그 신고 2026-07-09: PatchPlan 생성 시 LLM에게 전달되는 document_text가
"년 월 일2026 6 27"처럼 순서가 뒤섞여 나와, 실제 문서 검색(search_for)이
그 문자열을 못 찾아 patch가 계속 생성 실패했다.

원인: 일부 PDF(특히 "빈칸에 값 채우기" 방식으로 만들어진 한국 관공서·기업
양식)는 라벨("년","월","일")과 채워진 값("2026","6","27")을 서로 다른
시점에 별도로 그린다. pypdf/PyMuPDF의 기본 텍스트 추출은 PDF 내부의
"그리기 순서"(content stream 순서)를 따르는데, 이게 실제 화면에 보이는
좌→우 읽는 순서와 다를 수 있다. 좌표(Y로 줄을 묶고 X로 정렬) 기준으로
재구성해야 실제 읽는 순서가 나온다.

Red → Green → Refactor
"""
import unittest
from pathlib import Path


def _build_scrambled_date_pdf(tmp_path: Path) -> Path:
    """
    실제 버그 문서의 날짜 필드 패턴을 흉내낸 합성 PDF를 만든다.

    "년 월 일" 라벨을 먼저 그리고, 그 다음 "2026" "6" "27" 값을 시각적으로는
    라벨 사이사이에 위치하도록(같은 Y좌표, 다른 X좌표) 별도로 그린다 —
    실제 문서에서 관찰된 것과 동일하게 그리기 순서와 읽기 순서를 어긋나게 한다.
    """
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)

    # 라벨을 먼저 그린다 (그리기 순서상 앞) — x좌표는 값들 사이사이에 위치
    page.insert_text((235, 715), "년", fontsize=11, fontname="korea-s", color=(0, 0, 0))
    page.insert_text((295, 715), "월", fontsize=11, fontname="korea-s", color=(0, 0, 0))
    page.insert_text((345, 715), "일", fontsize=11, fontname="korea-s", color=(0, 0, 0))
    # 값을 나중에 그린다 (그리기 순서상 뒤) — 시각적으로는 라벨보다 왼쪽에 위치
    page.insert_text((190, 715), "2026", fontsize=11, fontname="helv", color=(0, 0, 0))
    page.insert_text((265, 715), "6", fontsize=11, fontname="helv", color=(0, 0, 0))
    page.insert_text((315, 715), "27", fontsize=11, fontname="helv", color=(0, 0, 0))

    out = tmp_path / "scrambled_date.pdf"
    doc.save(str(out))
    doc.close()
    return out


class TestParsePdfReadingOrder(unittest.TestCase):
    """실제 화면에 보이는 순서대로 텍스트가 추출되는지 검증."""

    def setUp(self):
        import tempfile
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_visually_interleaved_text_extracted_in_reading_order(self):
        """
        [버그 수정] 라벨과 값이 그리기 순서와 다르게 그려져도, 추출 결과는
        실제 화면에 보이는 좌→우 순서("2026년 6월 27일")를 따라야 한다.
        """
        from parsers.pdf_parser import parse_pdf

        pdf_path = _build_scrambled_date_pdf(self.tmp_path)
        text, page_count = parse_pdf(pdf_path)

        self.assertEqual(page_count, 1)
        self.assertIn("2026년6월27일", text.replace(" ", ""))

    def test_returns_page_count(self):
        """[회귀] page_count는 그대로 정확히 반환된다."""
        from parsers.pdf_parser import parse_pdf

        pdf_path = _build_scrambled_date_pdf(self.tmp_path)
        _, page_count = parse_pdf(pdf_path)
        self.assertEqual(page_count, 1)

    def test_page_label_prefix_preserved(self):
        """[회귀] 페이지별 "[페이지 N]" 레이블은 그대로 유지된다."""
        from parsers.pdf_parser import parse_pdf

        pdf_path = _build_scrambled_date_pdf(self.tmp_path)
        text, _ = parse_pdf(pdf_path)
        self.assertIn("[페이지 1]", text)

    def test_normal_left_to_right_text_unaffected(self):
        """[회귀] 이미 정상 순서로 그려진 일반 텍스트는 그대로 정상 추출된다."""
        import fitz
        from parsers.pdf_parser import parse_pdf

        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 100), "합계 금액 1,000,000원", fontsize=11, fontname="korea-s", color=(0, 0, 0))
        pdf_path = self.tmp_path / "normal.pdf"
        doc.save(str(pdf_path))
        doc.close()

        text, _ = parse_pdf(pdf_path)
        self.assertIn("합계 금액 1,000,000원", text)

    def test_multi_page_pdf_extracts_all_pages(self):
        """[회귀] 여러 페이지 PDF는 페이지별로 모두 추출된다."""
        import fitz
        from parsers.pdf_parser import parse_pdf

        doc = fitz.open()
        for i in range(2):
            page = doc.new_page(width=595, height=842)
            page.insert_text((72, 100), f"페이지{i+1}본문", fontsize=11, fontname="korea-s", color=(0, 0, 0))
        pdf_path = self.tmp_path / "multi.pdf"
        doc.save(str(pdf_path))
        doc.close()

        text, page_count = parse_pdf(pdf_path)
        self.assertEqual(page_count, 2)
        self.assertIn("[페이지 1]", text)
        self.assertIn("[페이지 2]", text)
        self.assertIn("페이지1본문", text.replace(" ", ""))
        self.assertIn("페이지2본문", text.replace(" ", ""))


if __name__ == "__main__":
    unittest.main()
