"""
pricing.estimate_cost_krw 테스트.

커버 범위:
  1. happy path — 알려진 모델의 정상 비용 계산 (원화 환산)
  2. unknown model — 가격표에 없는 모델은 예외 없이 0 반환
  3. boundary — 토큰 0건은 0 반환
"""
from decimal import Decimal

from django.test import SimpleTestCase

from apps.documents.services.pricing import USD_TO_KRW, estimate_cost_krw


class EstimateCostKrwTest(SimpleTestCase):
    def test_known_model_computes_expected_krw_cost(self):
        """claude-sonnet-4-6: input $3/1M, output $15/1M 기준으로 원화 환산 계산."""
        cost = estimate_cost_krw("claude-sonnet-4-6", input_tokens=1_000_000, output_tokens=1_000_000)
        expected_usd = Decimal("3.0") + Decimal("15.0")
        self.assertEqual(cost, expected_usd * USD_TO_KRW)

    def test_unknown_model_returns_zero_without_raising(self):
        """가격표에 없는 모델은 예외 없이 0을 반환한다 (예측 가능한 비즈니스 상태)."""
        cost = estimate_cost_krw("unknown-model-xyz", input_tokens=1000, output_tokens=1000)
        self.assertEqual(cost, Decimal("0"))

    def test_zero_tokens_returns_zero(self):
        """토큰 사용량이 0이면 비용도 0이다 (경계값)."""
        cost = estimate_cost_krw("gpt-4o", input_tokens=0, output_tokens=0)
        self.assertEqual(cost, Decimal("0"))
