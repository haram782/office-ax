"""
LLM 호출 비용을 추정하는 순수 함수 모음.

가격표는 1M 토큰당 USD 단가 기준이며, 계산 결과는 원화(KRW)로 환산해 반환한다.
UsageEvent.estimated_cost는 호출 시점의 계산 결과를 스냅샷으로 저장하므로,
이후 이 가격표가 갱신되어도 과거 기록된 비용에는 영향을 주지 않는다.
"""
from __future__ import annotations

from decimal import Decimal

_TOKENS_PER_MILLION = Decimal("1_000_000")

# 모델별 1M 토큰당 USD 단가 (input/output)
LLM_PRICING: dict[str, dict[str, Decimal]] = {
    "claude-sonnet-4-6": {"input": Decimal("3.0"), "output": Decimal("15.0")},
    "claude-haiku-4-5": {"input": Decimal("0.8"), "output": Decimal("4.0")},
    "gpt-4o": {"input": Decimal("2.5"), "output": Decimal("10.0")},
    "gemini/gemini-2.0-flash": {"input": Decimal("0.075"), "output": Decimal("0.3")},
}

# MVP 고정 환율, 정기 갱신 필요
USD_TO_KRW = Decimal("1380")


def estimate_cost_krw(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    """
    model + 토큰 수로 예상 비용(KRW)을 계산한다.

    가격표에 없는 모델은 예측 가능한 비즈니스 상태(비용 미산정)이지 인프라
    실패가 아니므로, 예외를 던지지 않고 0을 반환한다.
    """
    pricing = LLM_PRICING.get(model)
    if pricing is None:
        return Decimal("0")

    cost_usd = (
        Decimal(input_tokens) / _TOKENS_PER_MILLION * pricing["input"]
        + Decimal(output_tokens) / _TOKENS_PER_MILLION * pricing["output"]
    )
    return cost_usd * USD_TO_KRW
