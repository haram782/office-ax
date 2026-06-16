import os
from .base import BaseLLMClient, AnalysisResult
from .openai_client import OpenAIClient
from .anthropic_client import AnthropicClient
from .mock_client import MockLLMClient

__all__ = ["BaseLLMClient", "AnalysisResult", "get_llm_client"]

_REGISTRY: dict[str, type[BaseLLMClient]] = {
    "openai": OpenAIClient,
    "anthropic": AnthropicClient,
    "mock": MockLLMClient,
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
