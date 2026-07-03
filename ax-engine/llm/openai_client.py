import json
import os
from openai import OpenAI
from .base import BaseLLMClient, AnalysisResult


class OpenAIClient(BaseLLMClient):
    def __init__(self) -> None:
        self._client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        self._model = os.environ.get("OPENAI_MODEL", "gpt-4o")

    def analyze(self, masked_text: str, system_prompt: str, **context) -> AnalysisResult:
        response = self._client.chat.completions.create(
            model=self._model,
            store=False,          # ZDR: 이 요청을 OpenAI 학습 데이터로 저장하지 않도록 명시
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": masked_text},
            ],
        )

        raw = response.choices[0].message.content or "{}"
        parsed: dict = json.loads(raw)

        return AnalysisResult(
            summary=parsed.get("summary", ""),
            detected_errors=parsed.get("errors", []),
            model_used=response.model,
            input_tokens=response.usage.prompt_tokens if response.usage else 0,
            output_tokens=response.usage.completion_tokens if response.usage else 0,
            provider="openai",
            token_source="provider_reported",
        )
