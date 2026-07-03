"""
OpenAIClient 단위 테스트.

OpenAI SDK를 mock 처리해 외부 API 호출 없이 검증한다.

커버 범위:
  1. 정상 호출 → AnalysisResult에 provider="openai", token_source="provider_reported"
  2. 실제 usage.prompt_tokens/completion_tokens가 그대로 반영됨
"""
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("OPENAI_API_KEY", "test-key")

from llm.openai_client import OpenAIClient


def _make_response(summary: str = "요약", errors: list | None = None,
                    prompt_tokens: int = 200, completion_tokens: int = 80,
                    model: str = "gpt-4o") -> MagicMock:
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(
        content=json.dumps({"summary": summary, "errors": errors or []})
    ))]
    response.model = model
    response.usage.prompt_tokens = prompt_tokens
    response.usage.completion_tokens = completion_tokens
    return response


class TestOpenAIClient(unittest.TestCase):
    """정상 동작 케이스."""

    @patch("llm.openai_client.OpenAI")
    def test_provider_and_token_source_reported(self, mock_openai_cls):
        """provider="openai", token_source="provider_reported"가 채워진다."""
        mock_instance = MagicMock()
        mock_instance.chat.completions.create.return_value = _make_response()
        mock_openai_cls.return_value = mock_instance

        client = OpenAIClient()
        result = client.analyze("본문", "시스템 프롬프트")

        self.assertEqual(result.provider, "openai")
        self.assertEqual(result.token_source, "provider_reported")
        self.assertEqual(result.input_tokens, 200)
        self.assertEqual(result.output_tokens, 80)


if __name__ == "__main__":
    unittest.main()
