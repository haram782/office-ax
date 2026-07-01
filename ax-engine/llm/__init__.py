import os
from .base import BaseLLMClient, AnalysisResult
from .openai_client import OpenAIClient
from .anthropic_client import AnthropicClient
from .mock_client import MockLLMClient
from .gemini_client import GeminiClient
from .claude_cli_client import ClaudeCodeCLIClient
from .ensemble_client import EnsembleClient

__all__ = [
    "BaseLLMClient",
    "AnalysisResult",
    "get_llm_client",
    "GeminiClient",
    "EnsembleClient",
]

_REGISTRY: dict[str, type[BaseLLMClient]] = {
    "openai": OpenAIClient,
    "anthropic": AnthropicClient,
    "mock": MockLLMClient,
    "gemini": GeminiClient,
    # 로컬 개발 전용 — Claude Code Pro 플랜 구독으로 API 과금 없이 사용
    "claude_cli": ClaudeCodeCLIClient,
    "ensemble": EnsembleClient,
}


def get_llm_client() -> BaseLLMClient:
    provider = os.environ.get("LLM_PROVIDER", "openai").lower()
    cls = _REGISTRY.get(provider)
    if cls is None:
        raise ValueError(
            f"지원하지 않는 LLM_PROVIDER: '{provider}'. "
            f"사용 가능한 값: {list(_REGISTRY)}"
        )
    return cls()
