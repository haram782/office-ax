"""
PatchPlan 생성 서비스 레이어.

documents/views.py(GeneratePatchPlanView)와 chat/tasks.py(notify_chat_response)가
공통으로 재사용한다.
"""
from __future__ import annotations

import os
from datetime import datetime
from uuid import uuid4

from celery import current_app
from celery.exceptions import CeleryError, TimeoutError as CeleryTimeoutError

from ..models import DocumentChange, DocumentVersion, UploadLog


class LLMParseError(Exception):
    """LLM 응답이 유효한 JSON이 아니거나 PatchPlan 스키마와 맞지 않을 때 발생."""


# XLSX 양식 operation — patch.expected_context 병합 대상
_XLSX_FORMAT_OPERATIONS = {"set_cell_style", "set_number_format", "set_formula"}


def _generate_patch_plan(prompt: str, file_context: dict) -> dict:
    """
    AX Engine 태스크를 통해 PatchPlan JSON을 생성한다.

    실제 LLM 호출은 ax-engine의 get_llm_client() 경로를 사용한다.
    따라서 로컬 Gemini CLI, OpenAI, Ensemble 등 LLM_PROVIDER 설정을
    backend가 직접 알 필요가 없다.

    :param prompt: 사용자 수정 요청 문자열
    :param file_context: filename, source_type, corrections, summary 등 파일 컨텍스트
    :raises LLMParseError: JSON 파싱 실패 또는 operations 필드 누락 시
    """
    timeout = int(os.environ.get("PATCH_PLAN_TASK_TIMEOUT", "180"))
    async_result = current_app.send_task(
        "tasks.generate_patch_plan",
        kwargs={"prompt": prompt, "file_context": file_context},
        queue="ax",
    )
    try:
        plan = async_result.get(timeout=timeout)
    except CeleryTimeoutError as exc:
        raise LLMParseError("PatchPlan 생성 태스크가 시간 내 완료되지 않았습니다.") from exc
    except CeleryError as exc:
        raise LLMParseError(f"PatchPlan 생성 태스크 실패: {exc}") from exc
    except Exception as exc:
        raise LLMParseError(f"PatchPlan 생성 태스크 실패: {exc}") from exc

    if not isinstance(plan, dict):
        raise LLMParseError("PatchPlan 생성 태스크가 dict가 아닌 결과를 반환했습니다.")
    if "operations" not in plan:
        raise LLMParseError("PatchPlan에 operations 필드가 없습니다.")

    # plan_id 누락 시 자동 생성
    if not plan.get("plan_id"):
        plan["plan_id"] = (
            f"plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
        )

    return plan


def _build_file_context(upload_log: UploadLog) -> dict:
    """LLM에 전달할 파일 컨텍스트를 upload_log.result에서 추출한다."""
    result = upload_log.result or {}
    snippet = result.get("snippet_data") or {}
    return {
        "filename": upload_log.original_filename,
        "source_type": result.get(
            "source_type",
            upload_log.file_structure.source_type if upload_log.file_structure else "",
        ),
        "corrections": snippet.get("corrections", []),
        "snippet_data": snippet,
        "summary": result.get("summary", ""),
        "errors": result.get("errors", []),
        "document_text": result.get("document_text", ""),
    }


def _get_valid_upload_log(upload_id: int, prompt: str, user) -> tuple[UploadLog, str]:
    """PatchPlan 생성 요청의 소유권, prompt, 업로드 상태를 검증한다."""
    upload_log = (
        UploadLog.objects
        .select_related("file_structure")
        .get(pk=upload_id)
    )

    # 소유권 검증 — 예측 가능한 업무 실패이므로 호출자가 사용자 메시지로 변환한다.
    if upload_log.user_id != user.pk:
        raise PermissionError("해당 문서에 대한 수정 권한이 없습니다.")

    stripped_prompt = (prompt or "").strip()
    if not stripped_prompt:
        raise ValueError("prompt 필드가 필요합니다.")

    if upload_log.status != UploadLog.Status.DONE:
        raise ValueError("분석이 완료된 문서만 수정 요청이 가능합니다.")

    return upload_log, stripped_prompt


def _create_changes(
    version: DocumentVersion, operations: list, plan_id: str
) -> list[dict]:
    """operations 배열을 DocumentChange 행으로 일괄 저장하고 응답용 dict 목록을 반환한다."""
    changes = []
    for op in operations:
        risk = op.get("risk") or {}
        patch = dict(op.get("patch") or {})
        # XLSX 양식 operation의 expected_context는 patch.expected_context로 병합 저장
        # (document-editing-ax-next-roadmap-v1-ko.md 4절)
        if op.get("operation") in _XLSX_FORMAT_OPERATIONS and op.get("expected_context"):
            patch["expected_context"] = op.get("expected_context")
        change = DocumentChange.objects.create(
            version=version,
            operation_id=op.get("operation_id", ""),
            plan_id=plan_id,
            format=op.get("format", ""),
            operation=op.get("operation", ""),
            title=op.get("title", ""),
            original=op.get("original") or "",
            replacement=op.get("replacement") or "",
            reason=op.get("reason", ""),
            confidence=float(op.get("confidence", 0.0)),
            anchor=op.get("anchor") or {},
            patch=patch,
            risk_level=risk.get("level", ""),
            status=DocumentChange.Status.PENDING,
        )
        changes.append({
            "id": change.pk,
            "operation_id": change.operation_id,
            "format": change.format,
            "operation": change.operation,
            "title": change.title,
            "original": change.original,
            "replacement": change.replacement,
            "reason": change.reason,
            "confidence": change.confidence,
            "anchor": change.anchor,
            "patch": change.patch,
            "status": change.status,
        })
    return changes


class PatchPlanService:
    """
    PatchPlan 생성 서비스.

    documents/views.GeneratePatchPlanView와 chat/tasks.notify_chat_response가 공유한다.
    소유권 검증은 호출자 책임이 아니라 이 서비스가 직접 수행한다.
    """

    @staticmethod
    def validate_request(upload_id: int, prompt: str, user) -> tuple[UploadLog, str]:
        """PatchPlan 요청을 검증하고 UploadLog와 정규화된 prompt를 반환한다."""
        return _get_valid_upload_log(upload_id, prompt, user)

    @staticmethod
    def build_file_context(upload_log: UploadLog) -> dict:
        """검증된 UploadLog에서 ax-engine에 전달할 파일 컨텍스트를 만든다."""
        return _build_file_context(upload_log)

    @staticmethod
    def persist_patch_plan(
        upload_log: UploadLog,
        prompt: str,
        user,
        patch_plan: dict,
    ) -> dict:
        """이미 생성된 PatchPlan을 DocumentVersion/DocumentChange로 저장한다."""
        if "operations" not in patch_plan:
            raise LLMParseError("PatchPlan에 operations 필드가 없습니다.")

        operations = patch_plan.get("operations", [])
        plan_id = patch_plan.get("plan_id", "")

        if not plan_id:
            plan_id = f"plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
            patch_plan["plan_id"] = plan_id

        # operations 빈 배열 → 버전 생성 없이 반환 (정상 케이스)
        if not operations:
            return {"version_id": None, "plan_id": plan_id, "changes": []}

        version = DocumentVersion.objects.create(
            upload_log=upload_log,
            created_by=user,
            status=DocumentVersion.Status.DRAFT,
            label=prompt[:100],
            summary=patch_plan.get("summary", ""),
            patch_plan=patch_plan,
        )
        changes = _create_changes(version, operations, plan_id)

        return {"version_id": version.pk, "plan_id": plan_id, "changes": changes}

    @staticmethod
    def generate(upload_id: int, prompt: str, user) -> dict:
        """
        upload_id로 UploadLog를 조회하고 PatchPlan을 생성한 뒤 DB에 저장한다.

        Args:
            upload_id: UploadLog PK
            prompt: 사용자 수정 요청 문자열
            user: 요청 주체 (소유권 검증에 사용)

        Returns:
            {"version_id": int|None, "plan_id": str, "changes": list[dict]}

        Raises:
            UploadLog.DoesNotExist: upload_id에 해당하는 UploadLog 없음
            PermissionError: 타인 소유 upload_log
            ValueError: upload_log.status != DONE
            LLMParseError: LLM이 유효한 PatchPlan JSON을 반환하지 않음
        """
        upload_log, prompt = PatchPlanService.validate_request(upload_id, prompt, user)
        file_context = _build_file_context(upload_log)
        patch_plan = _generate_patch_plan(prompt, file_context)
        return PatchPlanService.persist_patch_plan(upload_log, prompt, user, patch_plan)
