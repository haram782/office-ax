import json
import os
from anthropic import Anthropic
from .base import BaseLLMClient, AnalysisResult


class AnthropicClient(BaseLLMClient):
    def __init__(self) -> None:
        self._client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self._model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

    def analyze(self, masked_text: str, system_prompt: str, **context) -> AnalysisResult:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": masked_text}],
        )

        raw = response.content[0].text
        parsed: dict = json.loads(raw)

        return AnalysisResult(
            summary=parsed.get("summary", ""),
            detected_errors=parsed.get("errors", []),
            model_used=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
