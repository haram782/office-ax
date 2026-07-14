from __future__ import annotations

import os
import tempfile
from datetime import date, timedelta
from pathlib import Path

from celery import shared_task
from celery.utils.log import get_task_logger
from django.utils import timezone

from .models import DocumentVersion, IngestionWorkflow, UploadLog, UsageEvent
from .patcher import (
    _set_failed,
    collect_applied_changes,
    persist_patch_result,
    render_docx,
    render_hwp,
    render_pdf,
    render_pptx,
    render_xlsx,
)
from .services import ensure_original_version
from .services.usage import (
    analysis_status_for_result,
    is_unsupported_scan_result,
    record_usage_event,
    usage_metadata_from_result,
)

logger = get_task_logger(__name__)

# storage 보관 정책 — 업로드 후 이 일수가 지나면 cleanup_expired_uploads가 삭제 대상으로 간주한다
RETENTION_DAYS = 30


@shared_task(name="documents.detect_weekly_patterns")
def detect_weekly_patterns() -> dict:
    """
    매일 새벽 2시 실행 (Celery Beat 스케줄).

    알고리즘:
      최근 30일간 status=DONE 인 UploadLog를 (user, file_structure) 단위로 집계.
      동일 그룹 내 날짜 목록에서 연속 업로드 간격이 7±1일 인 streak 가 3회 이상이면
      해당 IngestionWorkflow 에 is_suggested=True 플래그를 설정한다.
    """
    window_start = timezone.now() - timedelta(days=30)

    logs = (
        UploadLog.objects
        .filter(uploaded_at__gte=window_start, status=UploadLog.Status.DONE)
        .values("user_id", "file_structure_id", "uploaded_at")
        .order_by("user_id", "file_structure_id", "uploaded_at")
    )

    # (user_id, file_structure_id) → [업로드 날짜, ...]
    groups: dict[tuple[int, int], list[date]] = {}
    for log in logs:
        key = (log["user_id"], log["file_structure_id"])
        groups.setdefault(key, []).append(log["uploaded_at"].date())

    suggested_count = 0
    for (user_id, fs_id), dates in groups.items():
        if not _has_weekly_pattern(dates):
            continue

        workflow, created = IngestionWorkflow.objects.get_or_create(
            user_id=user_id,
            file_structure_id=fs_id,
        )

        # 이미 활성화됐거나 제안 중인 경우 중복 처리 방지
        if workflow.is_active or workflow.is_suggested:
            continue

        workflow.is_suggested = True
        workflow.suggested_at = timezone.now()
        workflow.save(update_fields=["is_suggested", "suggested_at"])
        suggested_count += 1

        logger.info(
            "주기성 패턴 감지 → 자동화 제안 플래그 설정 | user_id=%s | fs_id=%s | 날짜=%s",
            user_id,
            fs_id,
            sorted(dates),
        )

    logger.info("detect_weekly_patterns 완료 | 신규 제안=%d건", suggested_count)
    return {"newly_suggested": suggested_count}


# 업로드 tmp 파일 정리 기준 — 분석·패치가 2일 넘게 걸릴 일은 없다
_TMP_MAX_AGE_DAYS = 2
# save_temp_file이 만드는 파일만 대상 (호스트 /tmp를 공용으로 쓰는 개발 환경 보호)
_TMP_DOCUMENT_SUFFIXES = (".xlsx", ".pdf", ".docx", ".pptx", ".hwp", ".csv", ".png", ".jpg", ".jpeg", ".webp", ".gif")


def _cleanup_stale_tmp_files(tmp_dir: Path) -> int:
    """
    tmp_dir에서 save_temp_file 패턴(tmp* + 문서 확장자)의 오래된 파일을 지운다.

    베타 스택의 공유 tmp 볼륨은 OS가 청소하지 않으므로 무한 증식을 막는다.
    파일별 삭제 실패는 전체 정리를 중단하지 않는다 (파일시스템 경계 — try/except).
    """
    cutoff_ts = (timezone.now() - timedelta(days=_TMP_MAX_AGE_DAYS)).timestamp()
    removed = 0
    for path in tmp_dir.glob("tmp*"):
        try:
            if path.suffix.lower() not in _TMP_DOCUMENT_SUFFIXES:
                continue
            if not path.is_file() or path.stat().st_mtime >= cutoff_ts:
                continue
            path.unlink()
            removed += 1
        except OSError as exc:
            logger.warning("tmp 파일 정리 실패 | path=%s | %s", path, exc)
    return removed


@shared_task(name="documents.cleanup_expired_uploads")
def cleanup_expired_uploads() -> dict:
    """
    매일 새벽 3시 실행 (Celery Beat 스케줄, 패턴 감지 2시 이후).

    RETENTION_DAYS가 지난 UploadLog를 bulk delete한다. 연결된 DocumentVersion 및
    storage의 file/artifact_file 정리는 pre_delete 시그널(models.py)에 위임한다.
    업로드 임시 파일(TMPDIR)의 오래된 잔여물도 함께 정리한다.
    """
    cutoff = timezone.now() - timedelta(days=RETENTION_DAYS)
    expired_qs = UploadLog.objects.filter(uploaded_at__lt=cutoff)

    # delete()는 (총 삭제 행 수, {모델 라벨: 개수}) 를 반환한다.
    # CASCADE로 DocumentVersion도 함께 지워지므로 UploadLog 건수만 따로 집계한다.
    _, deleted_by_model = expired_qs.delete()
    deleted_count = deleted_by_model.get("documents.UploadLog", 0)

    stale_tmp_removed = _cleanup_stale_tmp_files(Path(tempfile.gettempdir()))

    logger.info(
        "cleanup_expired_uploads 완료 | 삭제=%d건 | tmp 정리=%d건",
        deleted_count, stale_tmp_removed,
    )
    return {"deleted_count": deleted_count, "stale_tmp_removed": stale_tmp_removed}


@shared_task(name="documents.notify_analysis_complete")
def notify_analysis_complete(upload_id: int, result: dict) -> None:
    """
    AX Engine의 analyze_document 완료 후 디스패치됨.

    1. UploadLog를 DONE 상태로 갱신 (수동 업로드 폴링 대비 DB 캐싱)
    2. 연결된 활성 워크플로우의 phone_number로 카카오 알림톡 발송
       - 자동화가 없는 일회성 수동 업로드는 알림 없이 DB 갱신만 수행
       - 알림톡 실패는 분석 결과에 영향 없이 로그 기록 후 result에 오류 메타 저장
    """
    from notifications.kakao_alimtalk import AlimtalkPayload, AlimtalkError, send_alimtalk

    try:
        upload_log = (
            UploadLog.objects
            .select_related("user", "file_structure")
            .get(pk=upload_id)
        )
    except UploadLog.DoesNotExist:
        logger.error("notify_analysis_complete: UploadLog pk=%s 없음", upload_id)
        return

    # ── 1. UploadLog 결과 저장 ──────────────────────────────────────────────
    upload_log.result = result
    upload_log.status = UploadLog.Status.DONE
    upload_log.save(update_fields=["result", "status"])

    # ── 1-a. 사용량 이벤트 기록 (best-effort) ───────────────────────────────
    # 스캔본(미지원)은 FAILED + error_code로 기록해 크레딧 차감에서 제외한다
    record_usage_event(
        user=upload_log.user,
        upload_log=upload_log,
        event_type=UsageEvent.EventType.DOCUMENT_ANALYSIS,
        status=analysis_status_for_result(result),
        metadata=usage_metadata_from_result(
            result,
            source="analysis_callback",
            error_code="unsupported_scan" if is_unsupported_scan_result(result) else None,
        ),
    )

    # ── 1-b. 원본 DocumentVersion 자동 생성 (idempotent — 중복 생성 방지) ──
    ensure_original_version(upload_log)

    # ── 2. 알림톡 발송 (자동화 워크플로우 + 전화번호 있을 때만) ─────────────
    workflow = (
        IngestionWorkflow.objects
        .filter(
            user=upload_log.user,
            file_structure=upload_log.file_structure,
            is_active=True,
        )
        .first()
    )

    if not workflow or not workflow.phone_number:
        return

    if os.environ.get("MOCK_KAKAO", "False") == "True":
        phone = workflow.phone_number
        summary_preview = result.get("summary", "").split("\n")[0][:40]
        error_count = len(result.get("errors", []))
        logger.info(
            "\n"
            "┌─────────────────────────────────────────────┐\n"
            "│        [MOCK KAKAO NOTIFICATION]            │\n"
            "├─────────────────────────────────────────────┤\n"
            "│  수신번호 : %s\n"
            "│  서류명   : %s\n"
            "│  요약(1줄): %s\n"
            "│  오류건수 : %d건\n"
            "└─────────────────────────────────────────────┘",
            phone,
            upload_log.original_filename,
            summary_preview,
            error_count,
        )
        return

    try:
        payload = AlimtalkPayload(
            to=workflow.phone_number,
            doc_name=upload_log.original_filename,
            summary=result.get("summary", "요약 정보 없음"),
            error_count=len(result.get("errors", [])),
        )
        send_alimtalk(payload)
        logger.info(
            "알림톡 발송 완료 | upload_id=%s | phone=%s****",
            upload_id,
            workflow.phone_number[:4],
        )

    except AlimtalkError as exc:
        logger.error(
            "알림톡 발송 실패 | upload_id=%s | status_code=%s | error=%s",
            upload_id,
            exc.status_code,
            exc,
        )
        # 분석 결과에 알림 실패 메타를 기록 → 대시보드에서 재발송 유도 가능
        upload_log.result = {**result, "_notification_error": str(exc)}
        upload_log.save(update_fields=["result"])

    except Exception as exc:
        logger.exception("알림톡 예기치 않은 오류 | upload_id=%s", upload_id)
        upload_log.result = {**result, "_notification_error": f"예기치 않은 오류: {exc}"}
        upload_log.save(update_fields=["result"])


# source_type → artifact 파일 확장자 매핑 (저장 파일명 결정용)
_ARTIFACT_EXT_BY_SOURCE_TYPE: dict[str, str] = {
    "excel": "xlsx",
    "docx":  "docx",
    "pptx":  "pptx",
    "pdf":   "pdf",
    "hwp":   "hwp",
    "hwpx":  "hwpx",
}

# source_type → collect 단계에서 필터링할 operation 타입 목록
_OPERATIONS_BY_FORMAT: dict[str, list[str]] = {
    "excel": ["replace_cell", "set_cell_style", "set_number_format", "set_formula"],
    "docx":  ["replace_text"],
    "pptx":  ["replace_text"],
    "hwp":   ["replace_text"],
    "hwpx":  ["replace_text"],
    # replace_text: PDF readable에서 짧은 텍스트 치환 시 LLM이 생성한다.
    # render_pdf는 annotate가 아닌 operation을 모두 redact_overlay 방식으로
    # 처리하므로(patcher.py render_pdf) collect 필터에도 포함해야 한다.
    "pdf":   ["annotate", "redact_overlay", "replace_text"],
}

# source_type → render 함수 매핑 (patcher.py로 이전)
_RENDER_BY_FORMAT = {
    "excel": render_xlsx,
    "docx":  render_docx,
    "pptx":  render_pptx,
    "pdf":   render_pdf,
    "hwp":   render_hwp,
    "hwpx":  render_hwp,
}


@shared_task(name="documents.patch_document_version")
def patch_document_version(version_id: int) -> None:
    """
    draft 상태 DocumentVersion의 applied DocumentChange를 3단계로 처리한다.

    패치 성공 시 결과 bytes를 artifact_file에 저장한다 — GET 다운로드는
    이 저장본을 그대로 반환하며 재생성하지 않는다(멱등성 보장).

    단계:
      1. collect — applied change 수집 (collect_applied_changes)
      2. render  — 순수 변환 (render_xlsx / render_docx / ...)
      3. persist — DB + storage 갱신 (persist_patch_result)

    지원 포맷 외 source_type → version.status=failed (예측 가능한 업무 실패)
    """
    from .models import DocumentVersion

    try:
        version = (
            DocumentVersion.objects
            .select_related("upload_log", "upload_log__file_structure")
            .get(pk=version_id)
        )
    except DocumentVersion.DoesNotExist:
        logger.error("patch_document_version: DocumentVersion pk=%s 없음", version_id)
        return

    upload_log = version.upload_log

    # ── 원본 파일 존재 확인 ────────────────────────────────────────────────
    if not upload_log.file or not upload_log.file.storage.exists(upload_log.file.name):
        _set_failed(
            version,
            "원본 파일(upload_log.file)이 존재하지 않습니다.",
            "source_file_missing",
        )
        logger.error("patch_document_version: 원본 파일 없음 | version_id=%s", version_id)
        _record_patch_artifact_event(
            version, upload_log, UsageEvent.Status.FAILED,
            reason="source_file_missing",
        )
        return

    source_type = upload_log.file_structure.source_type if upload_log.file_structure else ""
    render_fn = _RENDER_BY_FORMAT.get(source_type)
    if render_fn is None:
        # 지원하지 않는 포맷 — 예측 가능한 업무 실패이므로 Result 패턴(_set_failed)으로 처리
        _set_failed(version, f"지원하지 않는 포맷: {source_type}", "unsupported_format")
        _record_patch_artifact_event(
            version, upload_log, UsageEvent.Status.FAILED,
            reason="unsupported_format", source_type=source_type,
        )
        return

    # ── 1단계: collect ─────────────────────────────────────────────────────
    operations = _OPERATIONS_BY_FORMAT.get(source_type)
    changes = collect_applied_changes(version, operations=operations)

    # ── 2단계: render (파일 읽기 + 순수 변환) ──────────────────────────────
    try:
        with upload_log.file.open("rb") as f:
            original_bytes = f.read()
    except Exception as exc:
        logger.error("patch_document_version: 원본 파일 읽기 실패 | version_id=%s | %s", version_id, exc)
        _set_failed(version, f"원본 파일 읽기 실패: {exc}", "source_file_read_error")
        _record_patch_artifact_event(
            version, upload_log, UsageEvent.Status.FAILED,
            reason="source_file_read_error", source_type=source_type,
        )
        return

    # render 함수 내부에서 처리하지 못한 예외(fitz.save 실패 등)를 여기서 잡아
    # version을 반드시 failed로 전환한다 — 미처리 예외로 'generating' 상태가
    # 영구히 남아 FE 무한 로딩으로 이어지는 것을 방지한다
    try:
        result = render_fn(original_bytes, changes)
    except Exception as exc:
        logger.exception(
            "patch_document_version: render 단계 예외 | version_id=%s | format=%s",
            version_id, source_type,
        )
        _set_failed(version, f"render 실패: {exc}", "render_exception")
        _record_patch_artifact_event(
            version, upload_log, UsageEvent.Status.FAILED,
            reason="render_exception", source_type=source_type,
        )
        return

    # ── 3단계: persist ─────────────────────────────────────────────────────
    ext = _ARTIFACT_EXT_BY_SOURCE_TYPE.get(source_type, "")
    persist_patch_result(version, result, ext, changes)

    # persist_patch_result가 version.status를 READY/FAILED로 확정한 뒤 기록한다
    final_status = (
        UsageEvent.Status.SUCCESS
        if version.status == DocumentVersion.Status.READY
        else UsageEvent.Status.FAILED
    )
    _record_patch_artifact_event(
        version, upload_log, final_status,
        source_type=source_type,
        applied_changes=len(result.applied_ids),
        failed_changes=len(result.failed_items),
        error_message=version.error_message if final_status == UsageEvent.Status.FAILED else None,
        # 영속화용 generic failure_code와 분리해 PatchResult가 직접 발급한 안정 코드만
        # UsageEvent metadata.reason으로 남긴다.
        reason=_primary_failure_code(result) if final_status == UsageEvent.Status.FAILED else None,
    )


def _record_patch_artifact_event(version, upload_log, status: str, **metadata) -> None:
    """patch_document_version 각 단계 종료 시점에 UsageEvent를 best-effort로 기록한다."""
    record_usage_event(
        user=upload_log.user,
        upload_log=upload_log,
        document_version=version,
        event_type=UsageEvent.EventType.PATCH_ARTIFACT_GENERATION,
        status=status,
        metadata={"version_id": version.pk, **{k: v for k, v in metadata.items() if v is not None}},
    )


def _primary_failure_code(result) -> str | None:
    """PatchResult 항목이 직접 제공한 대표 실패 코드만 반환한다."""
    for item in result.failed_items:
        if item.get("code"):
            return item["code"]
    for item in result.needs_confirmation_items:
        if item.get("code"):
            return item["code"]
    return None


# ── 핵심 알고리즘 ─────────────────────────────────────────────────────────────

def _has_weekly_pattern(
    dates: list[date],
    min_streak: int = 3,
    target_days: int = 7,
    tolerance: int = 1,
) -> bool:
    """
    날짜 목록에서 7일(±1일) 주기로 연속 업로드된 streak 가
    min_streak 회 이상인지 검사한다.

    예) [1일, 7일, 14일, 21일] → gap=[6,7,7] → streak=4 → True
        [1일, 7일, 20일, 27일] → gap=[6,13,7] → 13일 gap에서 streak 리셋 → False
    """
    sorted_dates = sorted(set(dates))  # 동일 날짜 중복 업로드 제거
    if len(sorted_dates) < min_streak:
        return False

    streak = 1
    for i in range(1, len(sorted_dates)):
        gap = (sorted_dates[i] - sorted_dates[i - 1]).days
        if abs(gap - target_days) <= tolerance:   # 6 ≤ gap ≤ 8
            streak += 1
            if streak >= min_streak:
                return True
        else:
            streak = 1  # 패턴이 끊기면 연속 카운트 초기화

    return False
