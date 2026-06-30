from __future__ import annotations

import base64
import json
import os
import subprocess
from datetime import date, timedelta

from celery import shared_task
from celery.utils.log import get_task_logger
from django.utils import timezone

from .models import DocumentVersion, IngestionWorkflow, UploadLog
from .services import ensure_original_version

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


@shared_task(name="documents.cleanup_expired_uploads")
def cleanup_expired_uploads() -> dict:
    """
    매일 새벽 3시 실행 (Celery Beat 스케줄, 패턴 감지 2시 이후).

    RETENTION_DAYS가 지난 UploadLog를 bulk delete한다. 연결된 DocumentVersion 및
    storage의 file/artifact_file 정리는 pre_delete 시그널(models.py)에 위임한다.
    """
    cutoff = timezone.now() - timedelta(days=RETENTION_DAYS)
    expired_qs = UploadLog.objects.filter(uploaded_at__lt=cutoff)

    # delete()는 (총 삭제 행 수, {모델 라벨: 개수}) 를 반환한다.
    # CASCADE로 DocumentVersion도 함께 지워지므로 UploadLog 건수만 따로 집계한다.
    _, deleted_by_model = expired_qs.delete()
    deleted_count = deleted_by_model.get("documents.UploadLog", 0)

    logger.info("cleanup_expired_uploads 완료 | 삭제=%d건", deleted_count)
    return {"deleted_count": deleted_count}


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


@shared_task(name="documents.patch_document_version")
def patch_document_version(version_id: int) -> None:
    """
    draft 상태 DocumentVersion의 applied DocumentChange를 검증하고
    applied_change_ids를 기록 후 version.status = ready로 전환한다.

    패치 성공 시 결과 bytes를 artifact_file에 저장한다 — GET 다운로드는
    이 저장본을 그대로 반환하며 재생성하지 않는다(멱등성 보장).

    포맷 디스패치:
      - excel       → _patch_xlsx  (bytes 반환 여부 확인)
      - docx        → _patch_docx
      - pptx        → _patch_pptx
      - pdf         → _patch_pdf
      - hwp/hwpx    → _patch_hwp
      - 그 외       → version.status=failed (Result 패턴 — 지원 포맷 누락은 예측 가능한 업무 실패)
    """
    from django.core.files.base import ContentFile

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
        _set_failed(version, "원본 파일(upload_log.file)이 존재하지 않습니다.")
        logger.error("patch_document_version: 원본 파일 없음 | version_id=%s", version_id)
        return

    # ── 포맷별 패처 디스패치 ──────────────────────────────────────────────
    source_type = upload_log.file_structure.source_type if upload_log.file_structure else ""

    dispatchers = {
        "excel": _patch_xlsx,
        "docx":  _patch_docx,
        "pptx":  _patch_pptx,
        "pdf":   _patch_pdf,
        "hwp":   _patch_hwp,
        "hwpx":  _patch_hwp,
    }
    patcher = dispatchers.get(source_type)
    if patcher is None:
        # 지원하지 않는 포맷 — 예측 가능한 업무 실패이므로 Result 패턴(_set_failed)으로 처리
        _set_failed(version, f"지원하지 않는 포맷: {source_type}")
        return

    # _patch_* 함수는 bytes를 반환하거나 None(실패) 반환
    # 실패 처리는 각 함수 내부에서 _set_failed로 수행한다
    result_bytes = patcher(version, upload_log)
    if result_bytes is None:
        return

    # ── artifact 파일 저장 — 인프라 경계(스토리지 I/O)이므로 try/except로 격리 ──
    ext = _ARTIFACT_EXT_BY_SOURCE_TYPE.get(source_type, "")
    try:
        version.artifact_file.save(
            f"v{version.pk}.{ext}", ContentFile(result_bytes), save=False,
        )
        version.artifact_format = ext
        version.save(update_fields=["artifact_file", "artifact_format", "updated_at"])
    except Exception as exc:
        logger.exception(
            "patch_document_version: artifact_file 저장 실패 | version_id=%s", version_id,
        )
        _set_failed(version, f"결과 파일 저장 실패: {exc}")


def _set_failed(version: "DocumentVersion", error_message: str) -> None:
    """version 상태를 FAILED로 설정하고 에러 메시지를 저장한다."""
    from .models import DocumentVersion as _DV
    version.status = _DV.Status.FAILED
    version.error_message = error_message
    version.save(update_fields=["status", "error_message", "updated_at"])


def _patch_xlsx(version: "DocumentVersion", upload_log: "UploadLog") -> bytes | None:
    """
    XLSX 파일에 replace_cell 변경 항목을 반영한 bytes를 반환한다.

    처리 흐름:
      1. openpyxl로 원본 로드 (data_only=False — 수식 보존)
      2. replace_cell + status=applied 변경 순회
         - 시트/셀 값 불일치 → change.status=failed
         - 일치 → 셀 값 교체
      3. 성공 항목이 하나라도 있으면 수정된 XLSX bytes 반환
         하나도 없으면 version.status=failed, None 반환
    """
    import io

    import openpyxl

    from .models import DocumentChange, DocumentVersion

    try:
        with upload_log.file.open("rb") as f:
            wb = openpyxl.load_workbook(f, data_only=False)
    except Exception as exc:
        _set_failed(version, f"XLSX 로드 실패: {exc}")
        logger.error("patch_document_version: XLSX 로드 실패 | version_id=%s | %s", version.pk, exc)
        return None

    changes = DocumentChange.objects.filter(
        version=version,
        operation="replace_cell",
        status=DocumentChange.Status.APPLIED,
    )

    applied_ids: list[str] = []
    for change in changes:
        sheet_name = change.anchor.get("sheet", "")
        cell_ref = change.anchor.get("cell", "")

        if sheet_name not in wb.sheetnames:
            change.status = DocumentChange.Status.FAILED
            change.save(update_fields=["status", "updated_at"])
            logger.warning("patch_document_version: 시트 없음 | sheet=%s | op=%s", sheet_name, change.operation_id)
            continue

        ws = wb[sheet_name]
        current_value = str(ws[cell_ref].value) if ws[cell_ref].value is not None else ""

        if current_value != change.original:
            change.status = DocumentChange.Status.FAILED
            change.save(update_fields=["status", "updated_at"])
            logger.warning(
                "patch_document_version: 원본 값 불일치 | op=%s | expected=%r actual=%r",
                change.operation_id, change.original, current_value,
            )
            continue

        ws[cell_ref] = change.replacement
        applied_ids.append(change.operation_id)

    if not applied_ids:
        _set_failed(version, "적용 가능한 replace_cell 변경 항목이 없습니다.")
        return None

    output = io.BytesIO()
    wb.save(output)

    # version 상태만 갱신 — 파일 저장 없음 (on-demand 재생성)
    version.applied_change_ids = applied_ids
    version.status = DocumentVersion.Status.READY
    version.save(update_fields=["applied_change_ids", "status", "updated_at"])

    return output.getvalue()


def _patch_docx(version: "DocumentVersion", upload_log: "UploadLog") -> bytes | None:
    """
    DOCX 파일에 replace_text 변경 항목을 반영한 bytes를 반환한다.

    처리 흐름:
      1. python-docx로 원본 로드
      2. replace_text + status=applied 변경 순회
         - anchor.text_match 문자열을 포함하는 단락을 찾아 run 재구성으로 교체
         - 일치 단락 없으면 change.status=failed
      3. 성공 항목이 하나라도 있으면 수정된 DOCX bytes 반환

    주의: run 경계를 재구성하는 방식으로 텍스트를 교체하므로
          폰트·색상·크기 서식은 첫 번째 run의 서식을 유지한다.
    """
    import io

    from .models import DocumentChange, DocumentVersion

    try:
        from docx import Document
    except ImportError:
        _set_failed(version, "python-docx 라이브러리가 설치되지 않았습니다.")
        return None

    try:
        with upload_log.file.open("rb") as f:
            doc = Document(f)
    except Exception as exc:
        _set_failed(version, f"DOCX 로드 실패: {exc}")
        logger.error("patch_document_version: DOCX 로드 실패 | version_id=%s | %s", version.pk, exc)
        return None

    changes = DocumentChange.objects.filter(
        version=version,
        operation="replace_text",
        status=DocumentChange.Status.APPLIED,
    )

    applied_ids: list[str] = []
    for change in changes:
        target_text = change.anchor.get("text_match", "")
        replaced = False

        for para in doc.paragraphs:
            full_text = "".join(run.text for run in para.runs)
            if target_text not in full_text:
                continue
            # run 경계를 재구성해 target_text를 replacement로 치환
            new_text = full_text.replace(target_text, change.replacement, 1)
            # 첫 번째 run에 전체 텍스트를 쓰고 나머지 run은 비운다
            if para.runs:
                para.runs[0].text = new_text
                for run in para.runs[1:]:
                    run.text = ""
            replaced = True
            break

        if not replaced:
            change.status = DocumentChange.Status.FAILED
            change.save(update_fields=["status", "updated_at"])
            logger.warning(
                "patch_document_version: 대상 텍스트 없음 | op=%s | text_match=%r",
                change.operation_id, target_text,
            )
            continue

        applied_ids.append(change.operation_id)

    if not applied_ids:
        _set_failed(version, "적용 가능한 replace_text 변경 항목이 없습니다.")
        return None

    output = io.BytesIO()
    doc.save(output)

    # version 상태만 갱신 — 파일 저장 없음 (on-demand 재생성)
    version.applied_change_ids = applied_ids
    version.status = DocumentVersion.Status.READY
    version.save(update_fields=["applied_change_ids", "status", "updated_at"])

    return output.getvalue()


def _patch_pptx(version: "DocumentVersion", upload_log: "UploadLog") -> bytes | None:
    """
    PPTX 파일에 replace_text 변경 항목을 반영한 bytes를 반환한다.

    처리 흐름:
      1. python-pptx로 원본 로드
      2. replace_text + status=applied 변경 순회
         - anchor.slide_index (0-based), anchor.shape_index (0-based) 로 셰이프 특정
         - shape_index가 슬라이드 범위를 벗어나면 change.status=failed
         - text_frame 단락 또는 표 셀에서 target_text를 replacement로 치환
      3. 성공 항목이 하나라도 있으면 수정된 PPTX bytes 반환
    """
    import io

    from .models import DocumentChange, DocumentVersion

    try:
        from pptx import Presentation
    except ImportError:
        _set_failed(version, "python-pptx 라이브러리가 설치되지 않았습니다.")
        return None

    try:
        with upload_log.file.open("rb") as f:
            prs = Presentation(f)
    except Exception as exc:
        _set_failed(version, f"PPTX 로드 실패: {exc}")
        logger.error("patch_document_version: PPTX 로드 실패 | version_id=%s | %s", version.pk, exc)
        return None

    changes = DocumentChange.objects.filter(
        version=version,
        operation="replace_text",
        status=DocumentChange.Status.APPLIED,
    )

    applied_ids: list[str] = []
    for change in changes:
        slide_index = change.anchor.get("slide_index", 0)
        shape_index = change.anchor.get("shape_index")
        target_text = change.anchor.get("text_match", "")

        if slide_index >= len(prs.slides):
            change.status = DocumentChange.Status.FAILED
            change.save(update_fields=["status", "updated_at"])
            logger.warning(
                "patch_document_version: 슬라이드 인덱스 초과 | slide=%s | op=%s",
                slide_index, change.operation_id,
            )
            continue

        slide = prs.slides[slide_index]

        if shape_index is not None and shape_index >= len(slide.shapes):
            change.status = DocumentChange.Status.FAILED
            change.save(update_fields=["status", "updated_at"])
            logger.warning(
                "patch_document_version: 셰이프 인덱스 초과 | shape=%s | op=%s",
                shape_index, change.operation_id,
            )
            continue

        # 대상 셰이프 목록 결정 (shape_index 지정 시 단일, 없으면 전체 순회)
        shapes = [slide.shapes[shape_index]] if shape_index is not None else list(slide.shapes)

        replaced = False
        for shape in shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    full_text = "".join(run.text for run in para.runs)
                    if target_text not in full_text:
                        continue
                    new_text = full_text.replace(target_text, change.replacement, 1)
                    if para.runs:
                        para.runs[0].text = new_text
                        for run in para.runs[1:]:
                            run.text = ""
                    replaced = True
                    break

            if replaced:
                break

            if shape.has_table:
                for row in shape.table.rows:
                    for cell in row.cells:
                        if target_text in cell.text:
                            # 테이블 셀 텍스트 교체 — 첫 단락 첫 run에 합쳐 쓴다
                            tf = cell.text_frame
                            for para in tf.paragraphs:
                                full_text = "".join(run.text for run in para.runs)
                                if target_text not in full_text:
                                    continue
                                new_text = full_text.replace(target_text, change.replacement, 1)
                                if para.runs:
                                    para.runs[0].text = new_text
                                    for run in para.runs[1:]:
                                        run.text = ""
                                replaced = True
                                break
                        if replaced:
                            break
                    if replaced:
                        break

        if not replaced:
            change.status = DocumentChange.Status.FAILED
            change.save(update_fields=["status", "updated_at"])
            logger.warning(
                "patch_document_version: 대상 텍스트 없음 | op=%s | text_match=%r",
                change.operation_id, target_text,
            )
            continue

        applied_ids.append(change.operation_id)

    if not applied_ids:
        _set_failed(version, "적용 가능한 replace_text 변경 항목이 없습니다.")
        return None

    output = io.BytesIO()
    prs.save(output)

    # version 상태만 갱신 — 파일 저장 없음 (on-demand 재생성)
    version.applied_change_ids = applied_ids
    version.status = DocumentVersion.Status.READY
    version.save(update_fields=["applied_change_ids", "status", "updated_at"])

    return output.getvalue()


def _patch_hwp(version: "DocumentVersion", upload_log: "UploadLog") -> bytes | None:
    """
    HWP 파일에 replace_text 변경 항목을 반영한다.

    처리 흐름:
      1. replace_text + status=applied DocumentChange 조회
      2. 원본 파일 읽기 → base64 인코딩
      3. changes를 worker 입력 형식으로 변환
      4. subprocess로 hwp_worker.mjs 호출 (stdin JSON → stdout JSON)
         - 타임아웃 30초
         - returncode != 0 이면 _set_failed (stderr 내용 포함)
      5. worker 결과 파싱
         - failed 항목 → DocumentChange.status = failed
         - applied 비어 있으면 _set_failed
         - output_b64 → bytes → artifact_file 저장
      6. version.status = ready
    """
    from django.conf import settings
    from django.core.files.base import ContentFile

    from .models import DocumentChange, DocumentVersion

    changes = list(DocumentChange.objects.filter(
        version=version,
        operation="replace_text",
        status=DocumentChange.Status.APPLIED,
    ))

    if not changes:
        _set_failed(version, "적용 가능한 replace_text 변경 항목이 없습니다.")
        return

    # 원본 파일 읽기 → base64
    try:
        with upload_log.file.open("rb") as f:
            input_b64 = base64.b64encode(f.read()).decode()
    except Exception as exc:
        _set_failed(version, f"HWP 파일 읽기 실패: {exc}")
        logger.error("patch_document_version: HWP 파일 읽기 실패 | version_id=%s | %s", version.pk, exc)
        return

    # worker 입력 payload 구성
    payload = {
        "input_b64": input_b64,
        "changes": [
            {
                "operation_id": c.operation_id,
                "original": c.original,
                "replacement": c.replacement,
                "anchor": c.anchor,
            }
            for c in changes
        ],
    }

    # Node 실행 경로 — 환경변수 NODE_PATH 오버라이드 허용
    node_bin = os.environ.get("NODE_PATH", "node")
    # settings.BASE_DIR은 backend/ 디렉터리 → 부모가 프로젝트 루트
    project_root = settings.BASE_DIR.parent
    worker_path = "backend/workers/hwp_worker.mjs"

    try:
        result = subprocess.run(
            [node_bin, worker_path],
            input=json.dumps(payload).encode(),
            capture_output=True,
            timeout=30,
            cwd=str(project_root),
        )
    except subprocess.TimeoutExpired:
        _set_failed(version, "HWP worker 타임아웃 (30초 초과)")
        logger.error("patch_document_version: HWP worker 타임아웃 | version_id=%s", version.pk)
        return
    except Exception as exc:
        _set_failed(version, f"HWP worker 실행 실패: {exc}")
        logger.error("patch_document_version: HWP worker 실행 실패 | version_id=%s | %s", version.pk, exc)
        return

    # returncode 검사
    if result.returncode != 0:
        stderr_msg = result.stderr.decode(errors="replace").strip()
        _set_failed(version, f"HWP worker 오류: {stderr_msg}")
        logger.error(
            "patch_document_version: HWP worker 비정상 종료 | version_id=%s | returncode=%s | stderr=%s",
            version.pk, result.returncode, stderr_msg,
        )
        return

    # worker stdout 파싱
    try:
        output = json.loads(result.stdout.decode())
    except Exception as exc:
        _set_failed(version, f"HWP worker 출력 파싱 실패: {exc}")
        logger.error("patch_document_version: HWP worker 출력 파싱 실패 | version_id=%s", version.pk)
        return None

    applied_ids: list[str] = output.get("applied", [])
    failed_items: list[dict] = output.get("failed", [])

    # 실패 항목 → DocumentChange.status 갱신
    failed_ids = {item["operation_id"] for item in failed_items}
    for change in changes:
        if change.operation_id in failed_ids:
            change.status = DocumentChange.Status.FAILED
            change.save(update_fields=["status", "updated_at"])

    if not applied_ids:
        _set_failed(version, "HWP worker: 적용된 변경 항목이 없습니다.")
        return None

    # output_b64 → bytes 디코딩 — 파일 저장 없음 (on-demand 재생성)
    try:
        hwp_bytes = base64.b64decode(output["output_b64"])
    except Exception as exc:
        _set_failed(version, f"HWP worker output_b64 디코딩 실패: {exc}")
        return None

    version.applied_change_ids = applied_ids
    version.status = DocumentVersion.Status.READY
    version.save(update_fields=["applied_change_ids", "status", "updated_at"])

    return hwp_bytes


def _patch_pdf(version: "DocumentVersion", upload_log: "UploadLog") -> bytes | None:
    """
    PDF 파일에 annotate / redact_overlay 변경 항목을 반영한다.

    처리 흐름:
      1. fitz.open()으로 원본 PDF 로드
      2. annotate + redact_overlay operation, status=applied 변경 순회
         - anchor.type = pdf_bbox  → page/rect 직접 사용 (page는 1-based → 0-based 변환)
         - anchor.type = text_match → search_for()로 rect 탐색, occurrence 번째 사용
         - rect를 못 찾으면 change.status=failed
      3. annotate: add_highlight_annot + set_info(content)
         redact_overlay: add_redact_annot → apply_redactions → insert_text
      4. 성공 항목이 하나라도 있으면 artifact 저장 + version.status=ready
    """
    import io

    from .models import DocumentChange, DocumentVersion

    try:
        import fitz
    except ImportError:
        _set_failed(version, "PyMuPDF(fitz) 라이브러리가 설치되지 않았습니다.")
        return None

    try:
        with upload_log.file.open("rb") as f:
            pdf_bytes = f.read()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        _set_failed(version, f"PDF 로드 실패: {exc}")
        logger.error("patch_document_version: PDF 로드 실패 | version_id=%s | %s", version.pk, exc)
        return None

    changes = DocumentChange.objects.filter(
        version=version,
        operation__in=["annotate", "redact_overlay"],
        status=DocumentChange.Status.APPLIED,
    )

    applied_ids: list[str] = []

    for change in changes:
        rect = _resolve_pdf_rect(doc, change.anchor)

        if rect is None:
            # anchor 해석 실패 — 텍스트 없음 또는 범위 초과
            change.status = DocumentChange.Status.FAILED
            change.save(update_fields=["status", "updated_at"])
            logger.warning(
                "patch_document_version: PDF anchor 해석 실패 | op=%s | anchor=%s",
                change.operation_id, change.anchor,
            )
            continue

        page_idx, fitz_rect = rect
        page = doc[page_idx]

        if change.operation == "annotate":
            _apply_pdf_annotate(page, fitz_rect, change)
        else:
            # redact_overlay
            _apply_pdf_redact_overlay(page, fitz_rect, change)

        applied_ids.append(change.operation_id)

    if not applied_ids:
        doc.close()
        _set_failed(version, "적용 가능한 PDF 변경 항목이 없습니다.")
        return None

    output = io.BytesIO()
    doc.save(output)
    doc.close()
    output.seek(0)

    # 파일 저장 없음 — on-demand 재생성 방식
    pdf_output = output.read()
    version.applied_change_ids = applied_ids
    version.status = DocumentVersion.Status.READY
    version.save(update_fields=["applied_change_ids", "status", "updated_at"])

    return pdf_output


def _resolve_pdf_rect(
    doc: "fitz.Document",
    anchor: dict,
) -> "tuple[int, fitz.Rect] | None":
    """
    anchor 딕셔너리에서 (0-based 페이지 인덱스, fitz.Rect)를 반환한다.

    pdf_bbox anchor: page(1-based) → 0-based 변환, rect 딕셔너리 → fitz.Rect
    text_match anchor: search_for()로 텍스트 위치 탐색, occurrence 번째 결과 반환
                       page 지정 시 해당 페이지만, 없으면 전체 페이지 순서대로 첫 번째

    반환 None: 텍스트 없음, 페이지 범위 초과, rect 정보 누락
    """
    import fitz

    anchor_type = anchor.get("type", "")

    if anchor_type == "pdf_bbox":
        # page는 1-based
        page_num = anchor.get("page", 1)
        page_idx = page_num - 1
        if page_idx < 0 or page_idx >= len(doc):
            return None
        r = anchor.get("rect", {})
        if not r:
            return None
        try:
            rect = fitz.Rect(r["x0"], r["y0"], r["x1"], r["y1"])
        except (KeyError, TypeError):
            return None
        return (page_idx, rect)

    if anchor_type == "text_match":
        target = anchor.get("target_text", "")
        if not target:
            return None
        # page 지정 시 해당 페이지만 탐색, 없으면 전체 순회
        page_hint = anchor.get("page")
        occurrence = max(1, anchor.get("occurrence", 1))

        if page_hint is not None:
            page_idx = int(page_hint) - 1  # 1-based → 0-based
            pages_to_search = [(page_idx, doc[page_idx])] if 0 <= page_idx < len(doc) else []
        else:
            pages_to_search = [(i, doc[i]) for i in range(len(doc))]

        hit_count = 0
        for idx, page in pages_to_search:
            rects = page.search_for(target)
            for r in rects:
                hit_count += 1
                if hit_count == occurrence:
                    return (idx, r)

        return None  # 텍스트 없음

    # 알 수 없는 anchor 타입 — 실패로 처리
    return None


def _apply_pdf_annotate(page: "fitz.Page", rect: "fitz.Rect", change: "DocumentChange") -> None:
    """
    지정 rect에 하이라이트 주석을 추가한다.

    comment 내용: change.replacement 우선, 비어 있으면 change.reason 사용
    """
    comment = change.replacement or getattr(change, "reason", "") or ""
    annot = page.add_highlight_annot(rect)
    annot.set_info(content=comment)
    annot.update()


def _apply_pdf_redact_overlay(
    page: "fitz.Page", rect: "fitz.Rect", change: "DocumentChange"
) -> None:
    """
    지정 rect 영역을 흰색으로 가린 뒤 replacement 텍스트를 overlay로 삽입한다.

    CJK 문자가 포함된 텍스트는 PyMuPDF 내장 CJK 폰트("korea-s")를 사용한다.
    (fitz.Font("cjk") 객체를 insert_text(font=...)로 넘기면 PyMuPDF 1.24.5에서
    TypeError가 발생해 Helvetica로 fallback되며 한글 글리프가 없어 텍스트가
    깨지는 문제가 있었음)
    순수 ASCII 텍스트는 기존처럼 기본 내장 폰트("helv")를 사용한다 —
    korea-s 폰트로 ASCII 문자를 그리면 글자 사이에 불필요한 폭이 생겨
    텍스트 추출 시 문자마다 공백이 끼는 부작용이 있기 때문이다.
    """
    # 1. 기존 텍스트 가림 (흰 배경)
    page.add_redact_annot(rect, fill=(1, 1, 1))
    page.apply_redactions()

    # 2. 새 텍스트 overlay
    font_size = change.patch.get("font_size", 11) if change.patch else 11
    replacement = change.replacement or ""
    fontname = "korea-s" if any(ord(ch) > 127 for ch in replacement) else "helv"

    page.insert_text(
        (rect.x0, rect.y1 - 2),
        replacement,
        fontsize=font_size,
        fontname=fontname,
        color=(0, 0, 0),
    )


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
