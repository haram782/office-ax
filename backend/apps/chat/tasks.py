from celery import shared_task
from celery.utils.log import get_task_logger

from apps.documents.models import UploadLog

logger = get_task_logger(__name__)


@shared_task(name="chat.notify_chat_response")
def notify_chat_response(chat_message_id: int, result: dict) -> None:
    """
    AX Engine analyze_document 완료 후 chat_message_id가 있을 때 디스패치됨.

    1. UploadLog DONE 처리
    2. 어시스턴트 ChatMessage 생성 (요약 + 오류 목록 + 다운로드 링크)
    3. UserActionLog 기록 (패턴 감지 고도화용)
    """
    from .models import ChatMessage, UserActionLog

    try:
        user_message = (
            ChatMessage.objects
            .select_related("session__user", "upload_log")
            .get(pk=chat_message_id)
        )
    except ChatMessage.DoesNotExist:
        logger.error("notify_chat_response: ChatMessage pk=%s 없음", chat_message_id)
        return

    # ── 1. UploadLog 갱신 ────────────────────────────────────────────────────
    if user_message.upload_log:
        user_message.upload_log.result = result
        user_message.upload_log.status = UploadLog.Status.DONE
        user_message.upload_log.save(update_fields=["result", "status"])

    # ── 2. 어시스턴트 응답 내용 구성 ──────────────────────────────────────────
    summary = result.get("summary", "분석을 완료하였습니다.")
    errors = result.get("errors", [])
    artifact_url = result.get("artifact_url", "")

    lines = [summary]
    if errors:
        lines.append(f"\n**감지된 오류 {len(errors)}건**")
        lines.extend(f"• {e}" for e in errors[:5])
    if artifact_url:
        lines.append(f"\n[보정된 파일 다운로드]({artifact_url})")

    # ── 스니펫: 파일 타입별 인라인 프리뷰 데이터 ────────────────────────────
    source_type   = result.get("source_type", "")
    slide_urls    = result.get("slide_urls", [])
    docx_page_urls = result.get("docx_page_urls", [])
    has_snippet    = False
    snippet_data: dict = {}

    if source_type == "pptx":
        # PPTX: 슬라이드 이미지 URL 배열 + AI 패치용 구조화 데이터
        has_snippet  = True
        snippet_data = {
            "type":             "pptx_preview",
            "upload_log_id":    user_message.upload_log_id,
            "slide_urls":       slide_urls,
            "slide_count":      len(slide_urls),
            # AI가 특정 셰이프를 지정해 패치할 수 있도록 구조 트리 포함
            "pptx_structured":  result.get("pptx_structured", []),
            # slide_urls 가 비어있으면 LibreOffice 미설치 상태
            "render_available": bool(slide_urls),
        }
    elif source_type == "docx":
        # DOCX: LibreOffice+pdftoppm로 생성한 페이지별 PNG URL 배열
        has_snippet  = bool(docx_page_urls)
        snippet_data = {
            "type":             "docx_pages",
            "page_urls":        docx_page_urls,
            "page_count":       len(docx_page_urls),
            "render_available": bool(docx_page_urls),
        }
    elif artifact_url:
        # Excel / CSV / 기타: artifact + 교정 스니펫
        has_snippet  = True
        snippet_data = result.get("snippet_data") or {
            "type":         "excel_preview",
            "upload_log_id": user_message.upload_log_id,
            "headers":      ["날짜", "품목", "수량", "단가", "합계"],
            "preview_rows": [
                ["2024-01-03", "사무용품A", 10, 15000, 150000],
                ["2024-01-10", "사무용품B", 5,  3200,  16000],
                ["2024-01-15", "사무용품C", 8,  7500,  60000],
            ],
            "corrections": [
                {"cell": "D12", "original": "-15,000", "corrected": "15,000"},
                {"cell": "D27", "original": "-3,200",  "corrected": "3,200"},
                {"cell": "D31", "original": "-500",    "corrected": "500"},
                {"cell": "B34", "original": "#REF!",   "corrected": "=SUM(E2:E33)"},
            ],
        }

    # upload_log를 assistant 메시지에도 연결 — 프론트엔드가 id 기반 매칭을 할 수 있도록
    ChatMessage.objects.create(
        session=user_message.session,
        role=ChatMessage.Role.ASSISTANT,
        content="\n".join(lines),
        upload_log=user_message.upload_log,
        artifact_url=artifact_url,
        has_snippet=has_snippet,
        snippet_data=snippet_data,
    )

    # ── 3. 행동 로그 (sLLM 파인튜닝 데이터셋 축적) ───────────────────────────
    _SOURCE_TO_FILE_TYPE = {
        "xlsx":        UserActionLog.FileType.EXCEL,
        "excel":       UserActionLog.FileType.EXCEL,   # 레거시 호환
        "csv":         UserActionLog.FileType.CSV,
        "pdf_digital": UserActionLog.FileType.PDF_DIGITAL,
        "pdf_image":   UserActionLog.FileType.PDF_IMAGE,
        "docx":        UserActionLog.FileType.DOCX,
        "pptx":        UserActionLog.FileType.PPTX,
        "hwp":         UserActionLog.FileType.HWP,
        "image":       UserActionLog.FileType.IMAGE,
    }
    file_type = _SOURCE_TO_FILE_TYPE.get(
        result.get("source_type", "unknown"),
        UserActionLog.FileType.UNKNOWN,
    )

    UserActionLog.objects.create(
        user=user_message.session.user,
        session=user_message.session,
        upload_log=user_message.upload_log,
        action_type=UserActionLog.ActionType.ANALYSIS_DONE,
        file_type=file_type,
        action_tag=result.get("action_tag", "#문서_분석"),
        meta={
            "correction_count": len(errors),
            "has_artifact":     bool(artifact_url),
            "summary_length":   len(summary),
        },
    )

    logger.info(
        "채팅 응답 생성 완료 | session=%s | chat_msg=%s | artifact=%s",
        user_message.session_id,
        chat_message_id,
        artifact_url or "없음",
    )
