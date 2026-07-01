from celery import current_app, shared_task
from celery.utils.log import get_task_logger

from apps.documents.models import UploadLog
from apps.documents.services import ensure_original_version
from apps.documents.services.patch_plan import LLMParseError, PatchPlanService
from .change_highlights import corrections_to_change_highlights

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

        # ── 1-b. 원본 DocumentVersion 자동 생성 (idempotent — 중복 생성 방지) ──
        ensure_original_version(user_message.upload_log)

    # ── 1-c. patch_intent: ax-engine에 PatchPlan 생성을 요청한다 ─────────────
    result_type = result.get("type")
    if result_type == "patch_intent":
        _handle_patch_intent(user_message, result)
        return

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
            # AX Engine이 제공하는 변경 영역 메타데이터 (없으면 빈 리스트)
            "change_highlights": result.get("change_highlights", []),
        }
    elif source_type == "docx":
        # DOCX: LibreOffice+pdftoppm로 생성한 페이지별 PNG URL 배열
        has_snippet  = bool(docx_page_urls)
        snippet_data = {
            "type":             "docx_pages",
            "page_urls":        docx_page_urls,
            "page_count":       len(docx_page_urls),
            "render_available": bool(docx_page_urls),
            # AX Engine이 제공하는 변경 영역 메타데이터
            "change_highlights": result.get("change_highlights", []),
        }
    elif artifact_url:
        # Excel / CSV / 기타: artifact + 교정 스니펫
        has_snippet  = True
        snippet_data = dict(
            result.get("snippet_data") or {
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
        )
        # change_highlights: 이미 있으면 유지, 없으면 corrections에서 파생
        if "change_highlights" not in snippet_data:
            top_highlights = result.get("change_highlights")
            if top_highlights:
                snippet_data["change_highlights"] = top_highlights
            else:
                fmt = "csv" if source_type == "csv" else "xlsx"
                snippet_data["change_highlights"] = corrections_to_change_highlights(
                    snippet_data.get("corrections", []),
                    upload_log_id=user_message.upload_log_id,
                    fmt=fmt,
                )
    elif source_type == "chat" or result_type == "qa":
        # 텍스트 Q&A 응답 — 폴링 종료 마커 제공
        # (upload_id 있는 의도 판별 qa, 없는 일반 텍스트 채팅 모두 포함)
        has_snippet  = True
        snippet_data = {"type": "qa"}

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


def _handle_patch_intent(user_message, result: dict) -> None:
    """
    type="patch_intent" 결과를 받아 ax-engine PatchPlan 태스크를 enqueue한다.

    예측 가능한 실패(upload 없음, 권한 오류, 미완료 상태)는
    로그 기록 후 오류 내용 ChatMessage로 처리한다.
    예외를 전파하지 않아 채팅 태스크가 실패로 처리되지 않도록 보장한다.
    """
    from .models import ChatMessage

    upload_id = result.get("upload_id")
    refined_prompt = result.get("refined_prompt", "")
    user = user_message.session.user
    session = user_message.session

    if not upload_id or not refined_prompt:
        # upload_id 또는 refined_prompt가 없으면 수정 계획 생성 불가
        ChatMessage.objects.create(
            session=session,
            role=ChatMessage.Role.ASSISTANT,
            content="수정 요청을 처리하려면 문서가 열려 있어야 합니다. 문서를 업로드한 후 다시 시도해 주세요.",
        )
        return

    try:
        upload_log, refined_prompt = PatchPlanService.validate_request(
            upload_id=upload_id,
            prompt=refined_prompt,
            user=user,
        )
        file_context = PatchPlanService.build_file_context(upload_log)
    except UploadLog.DoesNotExist:
        logger.error(
            "patch_intent 처리 실패: UploadLog 없음 | upload_id=%s | session=%s",
            upload_id, session.pk,
        )
        ChatMessage.objects.create(
            session=session,
            role=ChatMessage.Role.ASSISTANT,
            content="문서를 찾을 수 없습니다. 파일을 다시 업로드해 주세요.",
        )
        return
    except (PermissionError, ValueError) as exc:
        logger.warning(
            "patch_intent 처리 실패: %s | upload_id=%s | session=%s",
            exc, upload_id, session.pk,
        )
        ChatMessage.objects.create(
            session=session,
            role=ChatMessage.Role.ASSISTANT,
            content=f"수정 요청을 처리할 수 없습니다: {exc}",
        )
        return
    except Exception:
        logger.exception(
            "patch_intent 검증 중 예기치 않은 오류 | upload_id=%s | session=%s",
            upload_id, session.pk,
        )
        ChatMessage.objects.create(
            session=session,
            role=ChatMessage.Role.ASSISTANT,
            content="내부 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
        )
        return

    try:
        current_app.send_task(
            "tasks.generate_patch_plan",
            kwargs={
                "prompt":           refined_prompt,
                "file_context":     file_context,
                "callback_task":    "chat.notify_patch_plan_generated",
                "callback_kwargs": {
                    "chat_message_id": user_message.pk,
                    "upload_id":       upload_log.pk,
                    "prompt":          refined_prompt,
                },
            },
            queue="ax",
        )
    except Exception:
        logger.exception(
            "PatchPlan 태스크 enqueue 실패 | upload_id=%s | session=%s",
            upload_log.pk, session.pk,
        )
        ChatMessage.objects.create(
            session=session,
            role=ChatMessage.Role.ASSISTANT,
            content="수정 계획 생성을 시작하지 못했습니다. 잠시 후 다시 시도해 주세요.",
        )
        return

    ChatMessage.objects.create(
        session=session,
        role=ChatMessage.Role.ASSISTANT,
        content="수정 계획을 생성하고 있습니다. 잠시 후 변경 항목을 확인해 주세요.",
    )

    logger.info(
        "patch_intent PatchPlan 태스크 enqueue | upload_id=%s | session=%s",
        upload_log.pk, session.pk,
    )


@shared_task(name="chat.notify_patch_plan_generated")
def notify_patch_plan_generated(
    chat_message_id: int,
    upload_id: int,
    prompt: str,
    result: dict,
) -> None:
    """
    ax-engine tasks.generate_patch_plan 완료 콜백.

    LLM이 만든 PatchPlan을 backend DB 모델로 저장하고 patch_plan 말풍선을 생성한다.
    """
    from .models import ChatMessage

    try:
        user_message = (
            ChatMessage.objects
            .select_related("session__user")
            .get(pk=chat_message_id)
        )
    except ChatMessage.DoesNotExist:
        logger.error("notify_patch_plan_generated: ChatMessage pk=%s 없음", chat_message_id)
        return

    session = user_message.session
    user = session.user

    if result.get("type") == "patch_plan_error" or result.get("error"):
        logger.error(
            "PatchPlan 생성 실패 콜백 | upload_id=%s | session=%s | error=%s",
            upload_id, session.pk, result.get("error"),
        )
        ChatMessage.objects.create(
            session=session,
            role=ChatMessage.Role.ASSISTANT,
            content="수정 계획 생성에 실패했습니다. 요청을 더 구체적으로 작성해 주세요.",
        )
        return

    try:
        upload_log, prompt = PatchPlanService.validate_request(
            upload_id=upload_id,
            prompt=prompt,
            user=user,
        )
        patch_result = PatchPlanService.persist_patch_plan(
            upload_log=upload_log,
            prompt=prompt,
            user=user,
            patch_plan=result,
        )
    except UploadLog.DoesNotExist:
        logger.error(
            "PatchPlan 저장 실패: UploadLog 없음 | upload_id=%s | session=%s",
            upload_id, session.pk,
        )
        ChatMessage.objects.create(
            session=session,
            role=ChatMessage.Role.ASSISTANT,
            content="문서를 찾을 수 없습니다. 파일을 다시 업로드해 주세요.",
        )
        return
    except (PermissionError, ValueError) as exc:
        logger.warning(
            "PatchPlan 저장 실패: %s | upload_id=%s | session=%s",
            exc, upload_id, session.pk,
        )
        ChatMessage.objects.create(
            session=session,
            role=ChatMessage.Role.ASSISTANT,
            content=f"수정 요청을 처리할 수 없습니다: {exc}",
        )
        return
    except LLMParseError as exc:
        logger.error(
            "PatchPlan 저장 중 스키마 오류 | upload_id=%s | session=%s | %s",
            upload_id, session.pk, exc,
        )
        ChatMessage.objects.create(
            session=session,
            role=ChatMessage.Role.ASSISTANT,
            content="수정 계획 형식이 올바르지 않습니다. 요청을 더 구체적으로 작성해 주세요.",
        )
        return
    except Exception:
        logger.exception(
            "PatchPlan 저장 중 예기치 않은 오류 | upload_id=%s | session=%s",
            upload_id, session.pk,
        )
        ChatMessage.objects.create(
            session=session,
            role=ChatMessage.Role.ASSISTANT,
            content="내부 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
        )
        return

    # 수정 계획 저장 성공 — patch_plan snippet_data로 ChatMessage 저장
    version_id = patch_result.get("version_id")
    changes = patch_result.get("changes", [])
    plan_id = patch_result.get("plan_id", "")

    if version_id is None:
        # operations 빈 배열 → 수정할 항목 없음 안내
        content = "요청하신 내용에 해당하는 수정 항목을 찾지 못했습니다. 더 구체적인 내용으로 다시 요청해 주세요."
        ChatMessage.objects.create(
            session=session,
            role=ChatMessage.Role.ASSISTANT,
            content=content,
        )
        return

    snippet_data = {
        "type":        "patch_plan",
        "version_id":  version_id,
        "upload_id":   upload_id,
        "plan_id":     plan_id,
        "changes":     changes,
    }

    ChatMessage.objects.create(
        session=session,
        role=ChatMessage.Role.ASSISTANT,
        content=f"수정 계획이 생성되었습니다. {len(changes)}개의 변경 항목을 확인해 주세요.",
        has_snippet=True,
        snippet_data=snippet_data,
    )

    logger.info(
        "patch_intent 처리 완료 | upload_id=%s | version_id=%s | changes=%d건 | session=%s",
        upload_id, version_id, len(changes), session.pk,
    )
