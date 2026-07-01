"""
text_chat Celery 태스크.
사용자 채팅 메시지를 LLM으로 처리하고 결과를 chat.notify_chat_response 콜백으로 전달한다.

upload_id가 전달되면 의도 판별 프롬프트(CHAT_INTENT_SYSTEM_PROMPT)로 전환해
Q&A/수정 요청을 구분한 결과를 반환한다.
"""
from __future__ import annotations

import json

from celery import shared_task
from celery.utils.log import get_task_logger

from llm import get_llm_client
from prompts.chat import CHAT_INTENT_SYSTEM_PROMPT, CHAT_SYSTEM_PROMPT

logger = get_task_logger(__name__)

# session_history 최대 항목 수 (초과분은 최신 기준으로 잘라낸다)
_MAX_HISTORY = 10


def _build_prompt(content: str, session_history: list[dict]) -> str:
    """
    session_history와 현재 메시지를 하나의 텍스트로 조합한다.
    LLM이 대화 맥락을 파악할 수 있도록 역할 레이블을 붙인다.
    """
    lines: list[str] = []

    # 최근 _MAX_HISTORY개만 포함
    recent = session_history[-_MAX_HISTORY:] if len(session_history) > _MAX_HISTORY else session_history
    for msg in recent:
        role = "사용자" if msg.get("role") == "user" else "어시스턴트"
        lines.append(f"[{role}] {msg.get('content', '')}")

    lines.append(f"[사용자] {content}")
    return "\n".join(lines)


def _send_callback(task_self, chat_message_id: int, result: dict) -> None:
    """chat.notify_chat_response 태스크를 통해 Django에 결과를 전달한다."""
    task_self.app.send_task(
        "chat.notify_chat_response",
        kwargs={"chat_message_id": chat_message_id, "result": result},
        queue="celery",
    )


def _parse_intent_response(raw: str) -> dict:
    """
    의도 판별 LLM 응답을 파싱한다.
    파싱 실패 시 안전하게 qa 타입으로 폴백한다.
    """
    text = raw.strip()
    # LLM이 마크다운 코드블록을 붙이는 경우 방어적 제거
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
    try:
        parsed = json.loads(text)
        if parsed.get("type") in ("qa", "patch_intent"):
            return parsed
    except (json.JSONDecodeError, ValueError):
        pass
    # 파싱 실패 — LLM 원문을 reply로 감싸 qa로 처리
    return {"type": "qa", "reply": raw}


def _run_text_chat(
    task_self,
    content: str,
    chat_message_id: int,
    session_history: list[dict],
    upload_id: int | None = None,
) -> dict:
    """
    실제 채팅 처리 로직. Celery 태스크와 분리해 단위 테스트가 가능하게 한다.

    Args:
        task_self: Celery 태스크 인스턴스 (retry 호출용)
        content: 사용자 메시지 텍스트
        chat_message_id: Django ChatMessage PK
        session_history: 최근 대화 이력
        upload_id: 현재 열람 중인 UploadLog PK (None이면 일반 Q&A 모드)
    """
    prompt_text = _build_prompt(content, session_history)

    # upload_id 있으면 의도 판별 프롬프트 사용
    system_prompt = CHAT_INTENT_SYSTEM_PROMPT if upload_id else CHAT_SYSTEM_PROMPT

    try:
        client = get_llm_client()
        result = client.analyze(
            prompt_text,
            system_prompt,
            mode="chat",
            chat_message_id=chat_message_id,
        )

        raw_reply = result.summary or "(응답 없음)"

        if upload_id:
            # 의도 판별 모드 — JSON 파싱 후 type 필드 포함 결과 반환
            intent = _parse_intent_response(raw_reply)
            intent_type = intent.get("type", "qa")

            if intent_type == "patch_intent":
                output = {
                    "type":           "patch_intent",
                    "refined_prompt": intent.get("refined_prompt", content),
                    "upload_id":      upload_id,
                    "summary":        "",
                    "errors":         [],
                    "source_type":    "chat",
                    "model_used":     result.model_used,
                }
            else:
                # qa 또는 파싱 실패 폴백
                reply = intent.get("reply", raw_reply)
                output = {
                    "type":        "qa",
                    "summary":     reply,
                    "upload_id":   upload_id,
                    "errors":      [],
                    "source_type": "chat",
                    "model_used":  result.model_used,
                }
        else:
            # 일반 Q&A 모드 — 기존 형식 유지 (하위 호환)
            output = {
                "summary":     raw_reply,
                "errors":      [],
                "source_type": "chat",
                "model_used":  result.model_used,
            }

        _send_callback(task_self, chat_message_id, output)
        return output

    except Exception as exc:
        logger.error(
            "text_chat 실패 | chat_message_id=%s | error=%s",
            chat_message_id, exc,
        )
        raise task_self.retry(exc=exc)


@shared_task(bind=True, name="tasks.text_chat", max_retries=2, default_retry_delay=10)
def text_chat(
    self,
    content: str,
    chat_message_id: int,
    session_history: list[dict] | None = None,
    upload_id: int | None = None,
) -> dict:
    """
    Django 백엔드의 ChatMessageCreateView 또는 직접 호출 진입점.

    Args:
        content: 사용자 메시지 텍스트
        chat_message_id: Django ChatMessage PK (콜백 라우팅용)
        session_history: 최근 대화 이력 [{"role": "user"|"assistant", "content": "..."}]
        upload_id: 현재 열람 중인 UploadLog PK — 있으면 의도 판별 모드로 전환
    """
    return _run_text_chat(self, content, chat_message_id, session_history or [], upload_id)
