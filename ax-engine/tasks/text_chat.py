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
from masking.pii_masker import mask_pii, unmask_pii
from prompts.chat import CHAT_INTENT_SYSTEM_PROMPT, CHAT_SYSTEM_PROMPT

logger = get_task_logger(__name__)

# session_history 최대 항목 수 (초과분은 최신 기준으로 잘라낸다)
_MAX_HISTORY = 10

# RAG 자산 주입 상한 — 자산당/전체 문자 수 (프롬프트 비대화 방지)
_RAG_PER_FILE_CHARS = 3000
_RAG_TOTAL_CHARS = 8000

# kind 값 → 프롬프트 표시 라벨
_RAG_KIND_LABELS = {"tone": "어투", "form": "양식"}


def _extract_rag_text(path: str) -> str:
    """
    RAG 자산 파일에서 텍스트를 추출한다.

    베타 규모(자산 소수·소용량)에서는 임베딩 검색 대신 전문 주입으로 충분하다.
    파일 접근·파싱 실패는 채팅을 깨지 않도록 빈 문자열로 격리한다 (파일시스템 경계).
    """
    from pathlib import Path

    suffix = Path(path).suffix.lower()
    try:
        if suffix == ".csv":
            from parsers.csv_parser import parse_csv
            text, _ = parse_csv(Path(path))
        elif suffix == ".xlsx":
            from parsers.excel_parser import parse_excel
            text, _ = parse_excel(Path(path))
        elif suffix == ".docx":
            from parsers.docx_parser import parse_docx
            text, _ = parse_docx(Path(path))
        elif suffix == ".pdf":
            from parsers.pdf_parser import parse_pdf
            text, _ = parse_pdf(Path(path))
        elif suffix == ".hwp":
            from parsers.hwp_parser import parse_hwp
            text, _ = parse_hwp(Path(path))
        else:
            return ""
        return (text or "")[:_RAG_PER_FILE_CHARS]
    except Exception as exc:
        logger.warning("RAG 자산 텍스트 추출 실패 | path=%s | %s", path, exc)
        return ""


def _build_rag_context(rag_files: list[dict] | None) -> str:
    """선택된 RAG 자산들을 프롬프트 참고 자료 블록으로 조합한다."""
    if not rag_files:
        return ""

    blocks: list[str] = []
    total = 0
    for item in rag_files:
        text = _extract_rag_text(item.get("path", ""))
        if not text:
            continue
        remain = _RAG_TOTAL_CHARS - total
        if remain <= 0:
            break
        text = text[:remain]
        total += len(text)
        label = _RAG_KIND_LABELS.get(item.get("kind", ""), item.get("kind", ""))
        blocks.append(f"[참고 자산 - {label}: {item.get('group_name', '')}]\n{text}")

    if not blocks:
        return ""
    return (
        "아래는 사용자가 지정한 참고 자산이다. 어투 자산은 문체·톤을 모방하고, "
        "양식 자산은 구조·형식을 따르라.\n\n" + "\n\n".join(blocks) + "\n\n"
    )


def _ensure_pii_values_present(refined_prompt: str, pii_mapping: dict[str, list[str]]) -> str:
    """
    의도 판별 LLM이 refined_prompt를 다시 쓰면서 마스킹 자리표시자를
    그대로 남기지도, 실제 값으로 풀어 쓰지도 않고 "사용자가 지정한
    값" 식으로 언급만 하고 지나가는 경우가 있다(실사용 재현). 이러면
    unmask_pii가 치환할 자리표시자 자체가 없어 실제 값이 refined_prompt
    어디에도 남지 않고, PatchPlan 생성 단계(원문 전송이 본질 — 결정
    11)가 값을 모른 채 작업을 하게 되어 LLM이 임의의(잘못된) 값으로
    채워 넣을 위험이 있다(실사용 재현: 사용자가 준 값 대신 사용자
    계정 이메일이 들어감). 복원 후에도 원본값이 빠져 있으면 명시적으로
    덧붙여 반드시 실제 값이 남게 한다.
    """
    missing = [
        original
        for originals in pii_mapping.values()
        for original in originals
        if original not in refined_prompt
    ]
    if not missing:
        return refined_prompt
    return refined_prompt + "\n\n(참고: 사용자가 실제로 제공한 값 — " + ", ".join(missing) + ")"


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


def _usage_fields(result) -> dict:
    """backend usage_metadata_from_result()가 UsageEvent 기록에 사용하는 계약 키를 만든다."""
    return {
        "usage": {
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "token_source": result.token_source,
        },
        "model": result.model_used,
        "provider": result.provider,
    }


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
    rag_files: list[dict] | None = None,
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
    # LLM 전송 전 PII 마스킹 — analyze_document와 동일 정책.
    # RAG 참고 자산도 마스킹 이전에 주입해 동일 정책을 적용받는다.
    # 상세: closed-beta-launch-plan-v1-ko.md 결정 11
    raw_prompt = _build_rag_context(rag_files) + _build_prompt(content, session_history)
    prompt_text, pii_counts, pii_mapping = mask_pii(raw_prompt)
    if pii_counts:
        logger.info("text_chat PII 마스킹 | chat_message_id=%s | counts=%s", chat_message_id, pii_counts)

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

        if upload_id:
            # 의도 판별 모드 — parsed_data에서 type을 직접 읽어 분기
            # (result.summary는 reply/summary 키만 추출하므로 patch_intent 응답에서 ""가 됨)
            intent = result.parsed_data if result.parsed_data.get("type") in ("qa", "patch_intent") \
                else _parse_intent_response(result.summary or "")
            intent_type = intent.get("type", "qa")

            if intent_type == "patch_intent":
                # PatchPlan 생성 단계는 원문 전송이 본질(결정 11) — 의도 판별
                # LLM 호출 자체는 마스킹된 텍스트로 하되, 사용자가 채팅으로
                # 직접 준 값(예: 문서에 적어달라고 요청한 이메일)은 여기서
                # 실제 값으로 복원해야 PatchPlan이 자리표시자를 "유효하지
                # 않은 값"으로 오인해 작업을 누락시키지 않는다.
                refined_prompt = intent.get("refined_prompt", content)
                if pii_mapping:
                    refined_prompt = unmask_pii(refined_prompt, pii_mapping)
                    refined_prompt = _ensure_pii_values_present(refined_prompt, pii_mapping)
                output = {
                    "type":           "patch_intent",
                    "refined_prompt": refined_prompt,
                    "upload_id":      upload_id,
                    "summary":        "",
                    "errors":         [],
                    "source_type":    "chat",
                    "model_used":     result.model_used,
                    **_usage_fields(result),
                }
            else:
                # qa 또는 파싱 실패 폴백
                reply = intent.get("reply", "") or result.summary or "(응답 없음)"
                output = {
                    "type":        "qa",
                    "summary":     reply,
                    "upload_id":   upload_id,
                    "errors":      [],
                    "source_type": "chat",
                    "model_used":  result.model_used,
                    **_usage_fields(result),
                }
        else:
            # 일반 Q&A 모드 — 기존 형식 유지 (하위 호환)
            output = {
                "chat_message_id": chat_message_id,
                "summary":         result.summary or "(응답 없음)",
                "errors":          [],
                "source_type":     "chat",
                "model_used":      result.model_used,
                **_usage_fields(result),
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
    rag_files: list[dict] | None = None,
) -> dict:
    """
    Django 백엔드의 ChatMessageCreateView 또는 직접 호출 진입점.

    Args:
        content: 사용자 메시지 텍스트
        chat_message_id: Django ChatMessage PK (콜백 라우팅용)
        session_history: 최근 대화 이력 [{"role": "user"|"assistant", "content": "..."}]
        upload_id: 현재 열람 중인 UploadLog PK — 있으면 의도 판별 모드로 전환
    """
    return _run_text_chat(self, content, chat_message_id, session_history or [], upload_id, rag_files)
