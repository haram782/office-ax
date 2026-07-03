"""
AnthropicClient 단위 테스트.

Anthropic SDK를 mock 처리해 외부 API 호출 없이 검증한다.

커버 범위:
  1. 정상 호출 → AnalysisResult에 provider="anthropic", token_source="provider_reported"
  2. 실제 usage.input_tokens/output_tokens가 그대로 반영됨
"""
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from llm.anthropic_client import AnthropicClient


def _make_response(summary: str = "요약", errors: list | None = None,
                    input_tokens: int = 120, output_tokens: int = 45,
                    model: str = "claude-sonnet-4-6") -> MagicMock:
    response = MagicMock()
    response.content = [MagicMock(text=json.dumps({"summary": summary, "errors": errors or []}))]
    response.model = model
    response.usage.input_tokens = input_tokens
    response.usage.output_tokens = output_tokens
    return response


class TestAnthropicClient(unittest.TestCase):
    """정상 동작 케이스."""

    @patch("llm.anthropic_client.Anthropic")
    def test_provider_and_token_source_reported(self, mock_anthropic_cls):
        """provider="anthropic", token_source="provider_reported"가 채워진다."""
        mock_instance = MagicMock()
        mock_instance.messages.create.return_value = _make_response()
        mock_anthropic_cls.return_value = mock_instance

        client = AnthropicClient()
        result = client.analyze("본문", "시스템 프롬프트")

        self.assertEqual(result.provider, "anthropic")
        self.assertEqual(result.token_source, "provider_reported")
        self.assertEqual(result.input_tokens, 120)
        self.assertEqual(result.output_tokens, 45)


if __name__ == "__main__":
    unittest.main()
