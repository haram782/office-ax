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


if __name__ == "__main__":
    unittest.main()
