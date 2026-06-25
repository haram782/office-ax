"""
EnsembleClient: 복수 LLM을 병렬 호출해 교차검증 결과를 반환하는 래퍼 클라이언트.

환경변수:
  LLM_ENSEMBLE_MODELS — 쉼표 구분 모델 목록 (예: openai,gemini)
                        미설정 시 ValueError
"""
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from .base import BaseLLMClient, AnalysisResult

logger = logging.getLogger(__name__)


def _get_registry() -> dict:
    """순환 참조 방지를 위해 런타임에 _REGISTRY를 lazy import한다."""
    from llm import _REGISTRY  # noqa: PLC0415
    return _REGISTRY


class EnsembleClient(BaseLLMClient):
    """
    여러 LLM 클라이언트를 병렬로 호출하고 교차검증으로 오류를 분류한다.

    - 2개 이상 클라이언트가 공통 감지한 오류 → confirmed (그대로 포함)
    - 단일 클라이언트만 감지한 오류 → candidate ('[후보] ' 접두사)
    - 요약: 성공 응답 중 summary 문자열이 가장 긴 것 선택
    """

    def __init__(self) -> None:
        models_env = os.environ.get("LLM_ENSEMBLE_MODELS", "").strip()
        if not models_env:
            raise ValueError(
                "LLM_ENSEMBLE_MODELS 환경변수가 설정되지 않았습니다. "
                "예: LLM_ENSEMBLE_MODELS=openai,gemini"
            )

        model_names = [m.strip() for m in models_env.split(",") if m.strip()]
        registry = _get_registry()

        self._clients: list[tuple[str, BaseLLMClient]] = []
        for name in model_names:
            cls = registry.get(name)
            if cls is None:
                raise ValueError(
                    f"앙상블에서 지원하지 않는 모델: '{name}'. "
                    f"사용 가능한 값: {list(registry)}"
                )
            self._clients.append((name, cls()))

        self._model_names = model_names

    def analyze(self, masked_text: str, system_prompt: str, **context) -> AnalysisResult:
        results = self._run_parallel(masked_text, system_prompt, **context)

        if not results:
            raise RuntimeError("앙상블 내 모든 LLM 클라이언트가 실패했습니다.")

        summary = self._select_summary(results)
        errors = self._cross_validate_errors(results)
        model_used = f"ensemble({','.join(self._model_names)})"

        return AnalysisResult(
            summary=summary,
            detected_errors=errors,
            model_used=model_used,
        )

    # ── 내부 헬퍼 ──────────────────────────────────────────────────────────────

    def _run_parallel(
        self, masked_text: str, system_prompt: str, **context
    ) -> list[AnalysisResult]:
        """ThreadPoolExecutor로 모든 클라이언트를 동시 실행한다."""
        results: list[AnalysisResult] = []

        with ThreadPoolExecutor(max_workers=len(self._clients)) as executor:
            futures = {
                executor.submit(client.analyze, masked_text, system_prompt, **context): name
                for name, client in self._clients
            }
            for future in as_completed(futures):
                name = futures[future]
                try:
                    results.append(future.result())
                except Exception as exc:
                    # 개별 클라이언트 실패는 로그만 기록하고 계속 진행 (부분 성공 허용)
                    logger.warning("앙상블 클라이언트 '%s' 실패: %s", name, exc)

        return results

    def _select_summary(self, results: list[AnalysisResult]) -> str:
        """summary 문자열이 가장 긴 결과를 반환한다."""
        return max((r.summary for r in results), key=len, default="")

    def _cross_validate_errors(self, results: list[AnalysisResult]) -> list[str]:
        """
        오류 교차검증:
          - 2개 이상 클라이언트가 감지한 오류 → confirmed (그대로 포함)
          - 단일 클라이언트만 감지한 오류 → candidate ('[후보] ' 접두사)
        중복 판단 기준: 텍스트 완전 일치
        """
        from collections import Counter

        # 모든 오류 텍스트 수집 (동일 결과 내 중복 제거)
        error_counts: Counter = Counter()
        for result in results:
            # 동일 클라이언트가 같은 오류를 두 번 내면 1회로 처리
            for err in set(result.detected_errors):
                error_counts[err] += 1

        confirmed: list[str] = []
        candidates: list[str] = []

        for err, count in error_counts.items():
            if count >= 2:
                confirmed.append(err)
            else:
                candidates.append(f"[후보] {err}")

        return confirmed + candidates
