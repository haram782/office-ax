"""
analyze_document Celery 태스크 단위 테스트.

커버 범위:
  1. 결과 dict에 backend usage_metadata_from_result 계약에 맞는
     usage.input_tokens / usage.output_tokens / usage.token_source / model / provider 포함
  2. 기존 하위 호환 키(model_used, tokens)도 유지되는지 확인
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from llm.base import AnalysisResult


def _make_result() -> AnalysisResult:
    return AnalysisResult(
        summary="분석 완료",
        detected_errors=[],
        model_used="gpt-4o",
        input_tokens=200,
        output_tokens=80,
        provider="openai",
        token_source="provider_reported",
    )


class TestAnalyzeDocumentUsageKeys(unittest.TestCase):
    """analyze_document 결과 dict의 usage/model/provider 키 검증."""

    @patch("tasks.analyze_document.get_llm_client")
    @patch("tasks.analyze_document.mask_pii")
    def test_result_contains_backend_contract_keys(
        self, mock_mask_pii, mock_get_client,
    ):
        """backend usage_metadata_from_result()가 기대하는 usage/model/provider 키가 채워진다."""
        mock_mask_pii.return_value = ("csv 마스킹 텍스트", {})

        mock_client = MagicMock()
        mock_client.analyze.return_value = _make_result()
        mock_get_client.return_value = mock_client

        from tasks.analyze_document import _SUFFIX_DISPATCH, analyze_document

        mock_parse_csv = MagicMock(return_value=("csv 원본 텍스트", {}))
        with patch.dict(_SUFFIX_DISPATCH, {".csv": (mock_parse_csv, "csv")}), \
             patch.object(analyze_document.app, "send_task"):
            output = analyze_document.run(file_path="/tmp/data.csv", upload_id=1)

        self.assertEqual(output["usage"]["input_tokens"], 200)
        self.assertEqual(output["usage"]["output_tokens"], 80)
        self.assertEqual(output["usage"]["token_source"], "provider_reported")
        self.assertEqual(output["model"], "gpt-4o")
        self.assertEqual(output["provider"], "openai")
        self.assertEqual(output["document_text"], "csv 마스킹 텍스트")


class TestScannedDocumentGuidance(unittest.TestCase):
    """
    스캔본 PDF·이미지 업로드 안내 테스트.

    closed-beta-launch-plan-v1-ko.md 갭 6 / M1:
      OCR이 미구현이므로 스캔본·이미지는 LLM 호출 없이
      "지원하지 않음" 안내를 분석 결과로 반환한다 (깨진 분석 결과 방지).
    """

    @patch("tasks.analyze_document.get_llm_client")
    def test_scanned_pdf_returns_guidance_without_llm(self, mock_get_client):
        """스캔 PDF(추출 텍스트 거의 없음)는 안내 문구를 반환하고 LLM을 호출하지 않는다."""
        mock_client = MagicMock()
        mock_client.analyze.return_value = _make_result()
        mock_get_client.return_value = mock_client

        from tasks.analyze_document import _SUFFIX_DISPATCH, analyze_document

        # 텍스트가 거의 없는 PDF → pdf_image 판별 경로
        mock_parse_pdf = MagicMock(return_value=("  ", {"pages": 1}))
        with patch.dict(_SUFFIX_DISPATCH, {".pdf": (mock_parse_pdf, None)}), \
             patch("parsers.ocr_parser.ocr_extract", return_value=("", {"ocr_engine": "unavailable"})), \
             patch.object(analyze_document.app, "send_task"):
            output = analyze_document.run(file_path="/tmp/scan.pdf", upload_id=7)

        self.assertIn("스캔", output["summary"])
        self.assertIn("지원하지 않", output["summary"])
        self.assertEqual(output["source_type"], "pdf_image")
        # LLM 미호출 — 비용·크레딧이 발생하면 안 된다
        mock_client.analyze.assert_not_called()

    @patch("tasks.analyze_document.get_llm_client")
    def test_image_upload_returns_guidance_without_llm(self, mock_get_client):
        """이미지 파일도 동일하게 안내 문구를 반환하고 LLM을 호출하지 않는다."""
        mock_client = MagicMock()
        mock_client.analyze.return_value = _make_result()
        mock_get_client.return_value = mock_client

        from tasks.analyze_document import _SUFFIX_DISPATCH, analyze_document

        mock_parse_image = MagicMock(return_value=("", {}))
        with patch.dict(_SUFFIX_DISPATCH, {".png": (mock_parse_image, "image")}), \
             patch.object(analyze_document.app, "send_task"):
            output = analyze_document.run(file_path="/tmp/photo.png", upload_id=8)

        self.assertIn("지원하지 않", output["summary"])
        mock_client.analyze.assert_not_called()

    @patch("tasks.analyze_document.get_llm_client")
    @patch("tasks.analyze_document.mask_pii")
    def test_digital_pdf_still_analyzed(self, mock_mask_pii, mock_get_client):
        """[회귀] 텍스트가 충분한 디지털 PDF는 기존대로 LLM 분석을 수행한다."""
        mock_mask_pii.return_value = ("마스킹된 본문", {})
        mock_client = MagicMock()
        mock_client.analyze.return_value = _make_result()
        mock_get_client.return_value = mock_client

        from tasks.analyze_document import _SUFFIX_DISPATCH, analyze_document

        mock_parse_pdf = MagicMock(return_value=("충분히 긴 디지털 PDF 본문 " * 50, {"pages": 3}))
        with patch.dict(_SUFFIX_DISPATCH, {".pdf": (mock_parse_pdf, None)}), \
             patch.object(analyze_document.app, "send_task"):
            output = analyze_document.run(file_path="/tmp/digital.pdf", upload_id=9)

        self.assertEqual(output["source_type"], "pdf_digital")
        self.assertEqual(output["summary"], "분석 완료")
        self.assertEqual(output["document_text"], "마스킹된 본문")
        mock_client.analyze.assert_called_once()



if __name__ == "__main__":
    unittest.main()
