from __future__ import annotations

import os
from datetime import date, timedelta

from celery import shared_task
from celery.utils.log import get_task_logger
from django.utils import timezone

from .models import IngestionWorkflow, UploadLog

logger = get_task_logger(__name__)


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
