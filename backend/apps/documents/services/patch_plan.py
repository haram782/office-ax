"""
PatchPlan 생성 서비스 레이어.

documents/views.py(GeneratePatchPlanView)와 chat/tasks.py(notify_chat_response)가
공통으로 재사용한다.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from uuid import uuid4

from ..models import DocumentChange, DocumentVersion, UploadLog


class LLMParseError(Exception):
    """LLM 응답이 유효한 JSON이 아니거나 PatchPlan 스키마와 맞지 않을 때 발생."""


# XLSX 양식 operation — patch.expected_context 병합 대상
_XLSX_FORMAT_OPERATIONS = {"set_cell_style", "set_number_format", "set_formula"}


_PATCH_PLAN_SYSTEM_PROMPT = """You are a document correction AI. Given a file's context and a user's edit request, generate a structured PatchPlan JSON.

Rules:
- Return ONLY valid JSON. No explanation text, no markdown code blocks.
- The JSON must have: schema, plan_id, summary, operations (array).
- operation_id: numbered "op_001", "op_002", ...
- Allowed operations: replace_cell, replace_text, annotate, set_cell_style, set_number_format, set_formula (XLSX/excel only — see rules below) (NOT redact_overlay or regenerate)
- Each operation must include: operation_id, format, operation, title, original, replacement, reason, confidence (0.0-1.0), anchor, patch
- anchor for XLSX: {"type": "cell", "sheet": "...", "cell": "A1"}
- anchor for text-based: {"type": "text_match", "target_text": "...", "occurrence": 1}
- risk: {"level": "low"|"medium"|"high"}
- If no changes are needed, return operations as empty array []
- Only generate a formatting/number-format/formula operation when the user explicitly asked for that kind of change within a range/cell you are confident about. If you are not confident about the exact range, the current cell values, or the target cell, do not generate the operation at all — an unconfident operation will simply be rejected by validation, so it is always safer to omit it.

set_cell_style (XLSX/Excel ONLY — never use this operation when format/source_type is not xlsx or excel):
- Only generate set_cell_style when the file's format/source_type is "xlsx" or "excel" AND the user explicitly asked for a formatting/style change (e.g. "헤더 보기 좋게 정리해줘"). Do not invent style changes the user did not ask for.
- operation_id, format="xlsx", operation="set_cell_style", title, reason, confidence, anchor, expected_context, patch are all required. original and replacement may be empty strings.
- anchor: {"type": "cell_range", "sheet": "...", "range": "A1:D1"}. Keep the range as small as possible (max 200 cells) — never select an entire sheet or an oversized range.
- expected_context is required and must include: "sample_values" (a dict of a few cell refs in the range mapped to their current text value, used to confirm you picked the right area) and "non_empty_cells" (a list of cell refs in the range that must not be blank, e.g. header cells).
- patch may ONLY contain these whitelisted keys — never add any other key, never use raw openpyxl/CSS property names: "font_bold" (boolean), "fill_color" (6-hex RRGGBB, no "#"), "horizontal_alignment" ("left"|"center"|"right"), "vertical_alignment" ("top"|"center"|"bottom"), "border" ("thin"|"medium"|"none").

set_number_format (XLSX/Excel ONLY):
- Only generate set_number_format when the user explicitly asked for a display-format change (e.g. "금액 열에 천 단위 콤마 붙여줘", "날짜 형식 통일해줘", "비율을 퍼센트로 표시해줘").
- operation_id, format="xlsx", operation="set_number_format", title, reason, confidence, anchor, expected_context, patch are all required. original and replacement may be empty strings.
- anchor: {"type": "cell_range", "sheet": "...", "range": "A1:D1"}, same 200-cell max as set_cell_style.
- expected_context is required, same shape as set_cell_style: "sample_values" and "non_empty_cells".
- patch may ONLY contain "number_format" (one of the following exact strings — never invent a different pattern) and "expected_context": "yyyy-mm-dd", "yyyy. mm. dd", "#,##0", "#,##0원", "#,##0.00", "0.0%", "0.00%".

set_formula (XLSX/Excel ONLY):
- Only generate set_formula when the user explicitly asked for a simple calculation (sum/average/count/min/max/simple conditional) to be written into ONE specific cell (e.g. "합계 행에 금액 합계를 넣어줘"). Never use it for row/column insertion or multi-cell formulas.
- operation_id, format="xlsx", operation="set_formula", title, reason, confidence, anchor, expected_context, patch are all required. original and replacement may be empty strings.
- anchor MUST be a single cell: {"type": "cell", "sheet": "...", "cell": "D5"}. Never use anchor.type="cell_range" for set_formula.
- expected_context is required and describes the data the formula reads (NOT the target cell, which is usually still empty): "sample_values" (a dict of a few cell refs the formula will sum/average/etc. mapped to their current value) and "non_empty_cells" (cell refs that must not be blank, typically the same data cells).
- patch may ONLY contain "formula" and "expected_context". formula must be a plain Excel formula string starting with "=" and MUST use only these whitelisted functions: SUM, AVERAGE, COUNT, COUNTA, MIN, MAX, IF (nesting is allowed, e.g. "=IF(COUNT(B2:B10)>0,SUM(B2:B10),0)").
- NEVER generate a formula containing: other-sheet or other-workbook references ("!" or "[...]"), URLs, string concatenation ("&"), or any function outside the whitelist (INDIRECT, HYPERLINK, WEBSERVICE, IMPORTRANGE, etc. are always forbidden). Such formulas will always be rejected — do not attempt them.

Return only JSON, starting with {"""


def _generate_patch_plan(prompt: str, file_context: dict) -> dict:
    """
    Anthropic Claude를 호출해 PatchPlan JSON을 생성한다.

    :param prompt: 사용자 수정 요청 문자열
    :param file_context: filename, source_type, corrections, summary 등 파일 컨텍스트
    :raises LLMParseError: JSON 파싱 실패 또는 operations 필드 누락 시
    """
    import anthropic  # lazy import — LLM 호출 시에만 의존

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

    context_json = json.dumps(
        file_context.get("corrections") or file_context.get("snippet_data") or {},
        ensure_ascii=False,
        indent=2,
    )
    user_message = (
        f"파일명: {file_context.get('filename', '알 수 없음')}\n"
        f"형식: {file_context.get('source_type', '알 수 없음')}\n"
        f"컨텍스트:\n{context_json}\n"
        f"수정 요청: {prompt}"
    )

    response = client.messages.create(
        model=model,
        max_tokens=2048,
        system=_PATCH_PLAN_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    raw = response.content[0].text.strip()

    # LLM이 실수로 마크다운 코드블록을 붙이는 경우 방어적 제거
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1]) if len(lines) > 2 else raw

    try:
        plan = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        raise LLMParseError(f"JSON 파싱 실패: {exc}") from exc

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
    }


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
        upload_log = (
            UploadLog.objects
            .select_related("file_structure")
            .get(pk=upload_id)
        )

        # 소유권 검증 — 예측 가능한 업무 실패이므로 PermissionError(표준 Python)로 처리
        if upload_log.user_id != user.pk:
            raise PermissionError("해당 문서에 대한 수정 권한이 없습니다.")

        if not prompt or not prompt.strip():
            raise ValueError("prompt 필드가 필요합니다.")

        if upload_log.status != UploadLog.Status.DONE:
            raise ValueError("분석이 완료된 문서만 수정 요청이 가능합니다.")

        file_context = _build_file_context(upload_log)
        patch_plan = _generate_patch_plan(prompt, file_context)

        operations = patch_plan.get("operations", [])
        plan_id = patch_plan.get("plan_id", "")

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
