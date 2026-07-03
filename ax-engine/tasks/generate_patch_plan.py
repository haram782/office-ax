from __future__ import annotations

import json
from datetime import datetime
from uuid import uuid4

from celery import shared_task
from celery.utils.log import get_task_logger

from llm import AnalysisResult, get_llm_client
from prompts.patch_plan import PATCH_PLAN_SYSTEM_PROMPT

logger = get_task_logger(__name__)


def _build_patch_plan_prompt(prompt: str, file_context: dict) -> str:
    """파일 컨텍스트와 사용자 요청을 LLM 입력 텍스트로 조립한다."""
    # corrections가 빈 배열([])이면 falsy이므로 명시적으로 비어있는지 확인
    corrections = file_context.get("corrections") or []
    snippet = file_context.get("snippet_data") or {}
    context_data = corrections or snippet or {}
    context_json = json.dumps(context_data, ensure_ascii=False, indent=2)

    summary = file_context.get("summary", "")

    lines = [
        f"파일명: {file_context.get('filename', '알 수 없음')}",
        f"형식: {file_context.get('source_type', '알 수 없음')}",
    ]
    if summary:
        lines.append(f"문서 요약:\n{summary}")
    if context_data:
        lines.append(f"세부 컨텍스트:\n{context_json}")
    lines.append(f"수정 요청: {prompt}")

    return "\n".join(lines)


def _strip_code_fence(raw: str) -> str:
    """LLM이 실수로 붙인 markdown code fence를 제거한다."""
    text = raw.strip()
    if not text.startswith("```"):
        return text
    lines = text.split("\n")
    return "\n".join(lines[1:-1]).strip() if len(lines) > 2 else text


def _coerce_patch_plan(result: AnalysisResult) -> dict:
    """AnalysisResult에서 PatchPlan dict를 추출하고 최소 스키마를 검증한다."""
    if result.parsed_data and isinstance(result.parsed_data, dict):
        plan = dict(result.parsed_data)
    else:
        raw = _strip_code_fence(result.summary or "")
        try:
            plan = json.loads(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"PatchPlan JSON 파싱 실패: {exc}") from exc

    if "operations" not in plan:
        raise ValueError("PatchPlan에 operations 필드가 없습니다.")

    if not plan.get("plan_id"):
        plan["plan_id"] = (
            f"plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
        )

    # 하위 호환용 — 신규 소비자는 usage/model/provider를 사용한다
    plan["model_used"] = result.model_used
    # backend usage_metadata_from_result()가 UsageEvent 기록에 사용하는 계약 키
    plan["usage"] = {
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "token_source": result.token_source,
    }
    plan["model"] = result.model_used
    plan["provider"] = result.provider
    return plan


def _run_generate_patch_plan(prompt: str, file_context: dict) -> dict:
    """LLM_PROVIDER에 맞는 클라이언트로 PatchPlan을 생성한다."""
    client = get_llm_client()
    prompt_text = _build_patch_plan_prompt(prompt, file_context)
    result = client.analyze(
        prompt_text,
        PATCH_PLAN_SYSTEM_PROMPT,
        mode="patch_plan",
        source_type=file_context.get("source_type", ""),
    )
    return _coerce_patch_plan(result)


def _send_callback(task_self, callback_task: str, callback_kwargs: dict, result: dict) -> None:
    """Django 콜백 태스크로 PatchPlan 생성 결과를 전달한다."""
    kwargs = dict(callback_kwargs or {})
    kwargs["result"] = result
    task_self.app.send_task(callback_task, kwargs=kwargs, queue="celery")


@shared_task(bind=True, name="tasks.generate_patch_plan", max_retries=2, default_retry_delay=10)
def generate_patch_plan(
    self,
    prompt: str,
    file_context: dict,
    callback_task: str | None = None,
    callback_kwargs: dict | None = None,
) -> dict:
    """
    PatchPlan 생성 태스크.

    callback_task가 있으면 Django 콜백으로 결과를 전달한다.
    callback_task가 없으면 호출자가 Celery result backend에서 반환값을 읽는다.
    """
    try:
        plan = _run_generate_patch_plan(prompt, file_context)
    except Exception as exc:
        logger.exception("PatchPlan 생성 실패 | filename=%s", file_context.get("filename"))
        if callback_task:
            _send_callback(
                self,
                callback_task,
                callback_kwargs or {},
                {"type": "patch_plan_error", "error": str(exc)},
            )
            return {"error": str(exc)}
        raise self.retry(exc=exc)

    if callback_task:
        _send_callback(self, callback_task, callback_kwargs or {}, plan)

    return plan
