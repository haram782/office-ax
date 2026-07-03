"""
EnsembleClient 단위 테스트.

커버 범위:
  1. 두 클라이언트 모두 성공 → confirmed/candidate 분리 검증
  2. 한 클라이언트 실패 → 성공 결과만 반환, 예외 없음
  3. 모든 클라이언트 실패 → RuntimeError
  4. LLM_ENSEMBLE_MODELS 미설정 → ValueError
  5. model_used 형식 검증: "ensemble(모델1,모델2)"
  6. 요약은 가장 긴 summary 선택
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from llm.base import AnalysisResult


def _make_result(
    summary: str, errors: list[str], model: str = "mock",
    provider: str = "", input_tokens: int = 0, output_tokens: int = 0,
    token_source: str = "provider_reported",
) -> AnalysisResult:
    return AnalysisResult(
        summary=summary, detected_errors=errors, model_used=model,
        provider=provider, input_tokens=input_tokens, output_tokens=output_tokens,
        token_source=token_source,
    )


def _make_mock_client(
    summary: str, errors: list[str], fail: bool = False,
    provider: str = "", input_tokens: int = 0, output_tokens: int = 0,
    token_source: str = "provider_reported",
):
    """가짜 LLM 클라이언트 생성 헬퍼."""
    client = MagicMock()
    if fail:
        client.analyze.side_effect = RuntimeError("클라이언트 오류")
    else:
        client.analyze.return_value = _make_result(
            summary, errors, provider=provider,
            input_tokens=input_tokens, output_tokens=output_tokens,
            token_source=token_source,
        )
    return client


class TestEnsembleClientSuccess(unittest.TestCase):
    """정상 동작 케이스."""

    def _make_client(self, models: list[tuple]):
        """
        models: [(이름, mock_client), ...]
        _REGISTRY와 LLM_ENSEMBLE_MODELS를 patch해 EnsembleClient 생성
        """
        from llm.ensemble_client import EnsembleClient

        registry = {name: (lambda c: type("C", (), {"__call__": lambda self: c})())(client)
                    for name, client in models}
        model_names = ",".join(name for name, _ in models)

        with patch.dict(os.environ, {"LLM_ENSEMBLE_MODELS": model_names}):
            with patch("llm.ensemble_client._get_registry", return_value={
                name: (lambda c: type("MockCls", (), {"__new__": lambda cls: c}))(client)
                for name, client in models
            }):
                # 직접 내부 클라이언트를 주입하는 방식 사용
                instance = EnsembleClient.__new__(EnsembleClient)
                instance._clients = [(name, client) for name, client in models]
                instance._model_names = [name for name, _ in models]
                return instance

    def test_both_succeed_confirmed_and_candidate(self):
        """두 클라이언트 모두 감지한 오류 → confirmed, 하나만 → candidate('[후보] ' 접두사)."""
        client_a = _make_mock_client(
            summary="짧은 요약",
            errors=["공통 오류", "A만 감지한 오류"],
        )
        client_b = _make_mock_client(
            summary="더 긴 요약입니다 두 번째 클라이언트",
            errors=["공통 오류", "B만 감지한 오류"],
        )

        ensemble = self._make_client([("a", client_a), ("b", client_b)])
        result = ensemble.analyze("문서 내용", "시스템 프롬프트")

        # 공통 오류는 그대로 포함
        self.assertIn("공통 오류", result.detected_errors)
        # A만 감지 → '[후보] ' 접두사
        candidates = [e for e in result.detected_errors if e.startswith("[후보] ")]
        candidate_texts = [e.removeprefix("[후보] ") for e in candidates]
        self.assertIn("A만 감지한 오류", candidate_texts)
        self.assertIn("B만 감지한 오류", candidate_texts)
        # '[후보] ' 없이 "A만 감지한 오류"가 직접 포함되면 안 됨
        self.assertNotIn("A만 감지한 오류", [e for e in result.detected_errors if not e.startswith("[후보] ")])

    def test_summary_is_longest(self):
        """요약은 성공한 응답 중 가장 긴 summary를 선택한다."""
        client_a = _make_mock_client(summary="짧음", errors=[])
        client_b = _make_mock_client(summary="이것이 훨씬 더 긴 요약입니다.", errors=[])

        ensemble = self._make_client([("a", client_a), ("b", client_b)])
        result = ensemble.analyze("내용", "프롬프트")

        self.assertEqual(result.summary, "이것이 훨씬 더 긴 요약입니다.")

    def test_model_used_format(self):
        """model_used는 'ensemble(모델1,모델2)' 형식."""
        client_a = _make_mock_client(summary="요약A", errors=[])
        client_b = _make_mock_client(summary="요약B", errors=[])

        ensemble = self._make_client([("openai", client_a), ("gemini", client_b)])
        result = ensemble.analyze("내용", "프롬프트")

        self.assertEqual(result.model_used, "ensemble(openai,gemini)")

    def test_one_client_fails_partial_success(self):
        """한 클라이언트 실패 → 성공한 클라이언트 결과만 반환, 예외 없음."""
        client_a = _make_mock_client(summary="정상 요약", errors=["오류1"])
        client_b = _make_mock_client(summary="", errors=[], fail=True)

        ensemble = self._make_client([("a", client_a), ("b", client_b)])
        result = ensemble.analyze("내용", "프롬프트")

        self.assertEqual(result.summary, "정상 요약")
        # 오류1은 하나의 클라이언트만 감지 → candidate
        self.assertIn("[후보] 오류1", result.detected_errors)

    def test_tokens_summed_across_successful_clients(self):
        """토큰 수는 성공한 클라이언트들의 값을 합산한다."""
        client_a = _make_mock_client(
            summary="요약A", errors=[], provider="openai",
            input_tokens=100, output_tokens=50, token_source="provider_reported",
        )
        client_b = _make_mock_client(
            summary="요약B", errors=[], provider="gemini",
            input_tokens=80, output_tokens=30, token_source="estimated",
        )

        ensemble = self._make_client([("openai", client_a), ("gemini", client_b)])
        result = ensemble.analyze("내용", "프롬프트")

        self.assertEqual(result.input_tokens, 180)
        self.assertEqual(result.output_tokens, 80)

    def test_provider_lists_all_participating_providers(self):
        """provider 필드는 참여한 클라이언트들의 provider를 콤마로 나열한다."""
        client_a = _make_mock_client(summary="요약A", errors=[], provider="openai")
        client_b = _make_mock_client(summary="요약B", errors=[], provider="gemini")

        ensemble = self._make_client([("openai", client_a), ("gemini", client_b)])
        result = ensemble.analyze("내용", "프롬프트")

        self.assertEqual(result.provider, "openai,gemini")

    def test_token_source_estimated_when_any_client_estimated(self):
        """참여 클라이언트 중 하나라도 estimated이면 앙상블 결과도 estimated로 표시한다."""
        client_a = _make_mock_client(
            summary="요약A", errors=[], provider="openai", token_source="provider_reported",
        )
        client_b = _make_mock_client(
            summary="요약B", errors=[], provider="gemini", token_source="estimated",
        )

        ensemble = self._make_client([("openai", client_a), ("gemini", client_b)])
        result = ensemble.analyze("내용", "프롬프트")

        self.assertEqual(result.token_source, "estimated")

    def test_token_source_provider_reported_when_all_reported(self):
        """모든 참여 클라이언트가 provider_reported면 앙상블 결과도 provider_reported."""
        client_a = _make_mock_client(
            summary="요약A", errors=[], provider="openai", token_source="provider_reported",
        )
        client_b = _make_mock_client(
            summary="요약B", errors=[], provider="anthropic", token_source="provider_reported",
        )

        ensemble = self._make_client([("openai", client_a), ("anthropic", client_b)])
        result = ensemble.analyze("내용", "프롬프트")

        self.assertEqual(result.token_source, "provider_reported")

    def test_all_clients_fail_raises_runtime_error(self):
        """모든 클라이언트 실패 → RuntimeError."""
        client_a = _make_mock_client(summary="", errors=[], fail=True)
        client_b = _make_mock_client(summary="", errors=[], fail=True)

        ensemble = self._make_client([("a", client_a), ("b", client_b)])
        with self.assertRaises(RuntimeError):
            ensemble.analyze("내용", "프롬프트")


class TestEnsembleClientInit(unittest.TestCase):
    """초기화 케이스."""

    def test_missing_env_var_raises_value_error(self):
        """LLM_ENSEMBLE_MODELS 미설정 시 ValueError."""
        env = {k: v for k, v in os.environ.items() if k != "LLM_ENSEMBLE_MODELS"}
        with patch.dict(os.environ, env, clear=True):
            # LLM_ENSEMBLE_MODELS 없는 환경에서 EnsembleClient 생성
            from llm.ensemble_client import EnsembleClient
            with self.assertRaises(ValueError):
                EnsembleClient()


if __name__ == "__main__":
    unittest.main()
