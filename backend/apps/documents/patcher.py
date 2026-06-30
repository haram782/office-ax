"""
문서 패치 순수화 모듈.

3단계 분리:
  collect_applied_changes  — DB에서 applied change 수집 (유일한 DB 읽기 지점)
  render_*                 — 순수 변환 함수: bytes in → PatchResult out, DB I/O 없음
  persist_patch_result     — 결과 영속화: DB + storage 갱신 (유일한 DB 쓰기 지점)

render_* 사용 규칙:
  - DocumentChange ORM 인스턴스를 인자로 받을 수 있다.
  - 단, 함수 안에서 .save() / .objects.filter() 등 DB 접근은 절대 하지 않는다.
  - 예외를 caller로 전파하지 않는다 — 모든 실패는 PatchResult.failed_items로 표현한다.
  - applied_ids가 비어있으면 output_bytes = b""로 설정한다.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import os
import subprocess
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ── 공용 결과 타입 ─────────────────────────────────────────────────────────────

@dataclass
class PatchResult:
    """render_* 함수의 반환 타입. DB I/O 없이 순수한 변환 결과만 담는다."""
    output_bytes: bytes
    applied_ids: list[str] = field(default_factory=list)
    failed_items: list[dict] = field(default_factory=list)
    # failed_items 원소 형식: {"operation_id": str, "reason": str}


# ── 1단계: collect ─────────────────────────────────────────────────────────────

def collect_applied_changes(version, operations: list[str] | None = None) -> list:
    """
    DB에서 version에 속한 status=APPLIED DocumentChange를 수집한다.

    operations: ["replace_cell"] 처럼 operation 타입 필터를 줄 수 있다.
                None이면 모든 operation 타입을 포함한다.
    """
    from .models import DocumentChange

    qs = DocumentChange.objects.filter(
        version=version,
        status=DocumentChange.Status.APPLIED,
    )
    if operations is not None:
        qs = qs.filter(operation__in=operations)
    return list(qs)


# ── 2단계: render — 순수 변환 ─────────────────────────────────────────────────

def render_xlsx(original_bytes: bytes, changes: list) -> PatchResult:
    """
    XLSX bytes + applied change 목록 → PatchResult.

    replace_cell operation: anchor.sheet / anchor.cell 으로 셀을 특정하고
    original과 실제 값이 일치하면 replacement로 교체한다.
    불일치·시트 없음 → failed_items에 기록.
    """
    import openpyxl

    try:
        wb = openpyxl.load_workbook(io.BytesIO(original_bytes), data_only=False)
    except Exception as exc:
        # 원본 파일 파싱 실패 — 모든 change를 failed로 처리
        return PatchResult(
            b"",
            [],
            [{"operation_id": c.operation_id, "reason": f"XLSX 로드 실패: {exc}"} for c in changes],
        )

    applied_ids: list[str] = []
    failed_items: list[dict] = []

    for change in changes:
        sheet_name = change.anchor.get("sheet", "")
        cell_ref = change.anchor.get("cell", "")

        if sheet_name not in wb.sheetnames:
            failed_items.append({
                "operation_id": change.operation_id,
                "reason": f"시트 없음: {sheet_name}",
            })
            logger.warning("render_xlsx: 시트 없음 | sheet=%s | op=%s", sheet_name, change.operation_id)
            continue

        ws = wb[sheet_name]
        current_value = str(ws[cell_ref].value) if ws[cell_ref].value is not None else ""

        if current_value != change.original:
            failed_items.append({
                "operation_id": change.operation_id,
                "reason": f"원본 값 불일치: expected={change.original!r}, actual={current_value!r}",
            })
            logger.warning(
                "render_xlsx: 원본 값 불일치 | op=%s | expected=%r actual=%r",
                change.operation_id, change.original, current_value,
            )
            continue

        ws[cell_ref] = change.replacement
        applied_ids.append(change.operation_id)

    if not applied_ids:
        return PatchResult(b"", [], failed_items)

    output = io.BytesIO()
    wb.save(output)
    return PatchResult(output.getvalue(), applied_ids, failed_items)


def render_docx(original_bytes: bytes, changes: list) -> PatchResult:
    """
    DOCX bytes + applied change 목록 → PatchResult.

    replace_text operation: anchor.text_match 문자열을 포함하는 단락을 찾아
    run 재구성 방식으로 교체한다. 일치 단락 없으면 failed_items에 기록.

    주의: 첫 번째 run의 서식을 유지하고 나머지 run을 비우는 방식이므로
          교체 후 폰트·크기는 첫 번째 run 서식을 따른다.
    """
    try:
        from docx import Document
    except ImportError:
        return PatchResult(
            b"",
            [],
            [{"operation_id": c.operation_id, "reason": "python-docx 미설치"} for c in changes],
        )

    try:
        doc = Document(io.BytesIO(original_bytes))
    except Exception as exc:
        return PatchResult(
            b"",
            [],
            [{"operation_id": c.operation_id, "reason": f"DOCX 로드 실패: {exc}"} for c in changes],
        )

    applied_ids: list[str] = []
    failed_items: list[dict] = []

    for change in changes:
        target_text = change.anchor.get("text_match", "")
        replaced = False

        for para in doc.paragraphs:
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

        if not replaced:
            failed_items.append({
                "operation_id": change.operation_id,
                "reason": f"대상 텍스트 없음: {target_text!r}",
            })
            logger.warning("render_docx: 대상 텍스트 없음 | op=%s | text_match=%r", change.operation_id, target_text)
            continue

        applied_ids.append(change.operation_id)

    if not applied_ids:
        return PatchResult(b"", [], failed_items)

    output = io.BytesIO()
    doc.save(output)
    return PatchResult(output.getvalue(), applied_ids, failed_items)


def render_pptx(original_bytes: bytes, changes: list) -> PatchResult:
    """
    PPTX bytes + applied change 목록 → PatchResult.

    replace_text operation: anchor.slide_index(0-based), anchor.shape_index(0-based),
    anchor.text_match 로 대상 텍스트를 특정해 교체한다.
    슬라이드·셰이프 범위 초과, 텍스트 없음 → failed_items에 기록.
    """
    try:
        from pptx import Presentation
    except ImportError:
        return PatchResult(
            b"",
            [],
            [{"operation_id": c.operation_id, "reason": "python-pptx 미설치"} for c in changes],
        )

    try:
        prs = Presentation(io.BytesIO(original_bytes))
    except Exception as exc:
        return PatchResult(
            b"",
            [],
            [{"operation_id": c.operation_id, "reason": f"PPTX 로드 실패: {exc}"} for c in changes],
        )

    applied_ids: list[str] = []
    failed_items: list[dict] = []

    for change in changes:
        slide_index = change.anchor.get("slide_index", 0)
        shape_index = change.anchor.get("shape_index")
        target_text = change.anchor.get("text_match", "")

        if slide_index >= len(prs.slides):
            failed_items.append({
                "operation_id": change.operation_id,
                "reason": f"슬라이드 인덱스 초과: {slide_index}",
            })
            continue

        slide = prs.slides[slide_index]

        if shape_index is not None and shape_index >= len(slide.shapes):
            failed_items.append({
                "operation_id": change.operation_id,
                "reason": f"셰이프 인덱스 초과: {shape_index}",
            })
            continue

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
                        if target_text not in cell.text:
                            continue
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
            failed_items.append({
                "operation_id": change.operation_id,
                "reason": f"대상 텍스트 없음: {target_text!r}",
            })
            continue

        applied_ids.append(change.operation_id)

    if not applied_ids:
        return PatchResult(b"", [], failed_items)

    output = io.BytesIO()
    prs.save(output)
    return PatchResult(output.getvalue(), applied_ids, failed_items)


def render_pdf(original_bytes: bytes, changes: list) -> PatchResult:
    """
    PDF bytes + applied change 목록 → PatchResult.

    annotate/redact_overlay operation: anchor로 rect를 해석하고 페이지에 적용한다.
    """
    try:
        import fitz
    except ImportError:
        return PatchResult(
            b"",
            [],
            [{"operation_id": c.operation_id, "reason": "PyMuPDF(fitz) 미설치"} for c in changes],
        )

    try:
        doc = fitz.open(stream=original_bytes, filetype="pdf")
    except Exception as exc:
        return PatchResult(
            b"",
            [],
            [{"operation_id": c.operation_id, "reason": f"PDF 로드 실패: {exc}"} for c in changes],
        )

    applied_ids: list[str] = []
    failed_items: list[dict] = []

    for change in changes:
        rect_result = _resolve_pdf_rect(doc, change.anchor)

        if rect_result is None:
            failed_items.append({
                "operation_id": change.operation_id,
                "reason": f"PDF anchor 해석 실패: {change.anchor}",
            })
            logger.warning("render_pdf: anchor 해석 실패 | op=%s | anchor=%s", change.operation_id, change.anchor)
            continue

        page_idx, fitz_rect = rect_result
        page = doc[page_idx]

        if change.operation == "annotate":
            _apply_pdf_annotate(page, fitz_rect, change)
        else:
            _apply_pdf_redact_overlay(page, fitz_rect, change)

        applied_ids.append(change.operation_id)

    if not applied_ids:
        doc.close()
        return PatchResult(b"", [], failed_items)

    output = io.BytesIO()
    doc.save(output)
    doc.close()
    output.seek(0)
    return PatchResult(output.read(), applied_ids, failed_items)


def render_hwp(original_bytes: bytes, changes: list) -> PatchResult:
    """
    HWP bytes + applied change 목록 → PatchResult.

    subprocess로 hwp_worker.mjs를 호출한다. subprocess 실패·타임아웃 시
    예외를 전파하지 않고 PatchResult(b"", [], all_failed) 형태로 반환한다.
    (업무 실패 — Result 패턴)
    """
    if not changes:
        return PatchResult(b"", [], [])

    from django.conf import settings

    input_b64 = base64.b64encode(original_bytes).decode()
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

    node_bin = os.environ.get("NODE_PATH", "node")
    project_root = settings.BASE_DIR.parent
    worker_path = "backend/workers/hwp_worker.mjs"

    def _all_failed(reason: str) -> PatchResult:
        return PatchResult(
            b"",
            [],
            [{"operation_id": c.operation_id, "reason": reason} for c in changes],
        )

    try:
        result = subprocess.run(
            [node_bin, worker_path],
            input=json.dumps(payload).encode(),
            capture_output=True,
            timeout=30,
            cwd=str(project_root),
        )
    except subprocess.TimeoutExpired:
        logger.error("render_hwp: HWP worker 타임아웃")
        return _all_failed("HWP worker 타임아웃 (30초 초과)")
    except Exception as exc:
        logger.error("render_hwp: HWP worker 실행 실패 | %s", exc)
        return _all_failed(f"HWP worker 실행 실패: {exc}")

    if result.returncode != 0:
        stderr_msg = result.stderr.decode(errors="replace").strip()
        logger.error("render_hwp: worker 비정상 종료 | returncode=%s | stderr=%s", result.returncode, stderr_msg)
        return _all_failed(f"HWP worker 오류: {stderr_msg}")

    try:
        output = json.loads(result.stdout.decode())
    except Exception as exc:
        return _all_failed(f"HWP worker 출력 파싱 실패: {exc}")

    applied_ids: list[str] = output.get("applied", [])
    failed_items: list[dict] = output.get("failed", [])

    if not applied_ids:
        return PatchResult(b"", [], failed_items)

    try:
        hwp_bytes = base64.b64decode(output["output_b64"])
    except Exception as exc:
        return _all_failed(f"HWP worker output_b64 디코딩 실패: {exc}")

    return PatchResult(hwp_bytes, applied_ids, failed_items)


# ── 3단계: persist — DB + storage 갱신 ─────────────────────────────────────────

def persist_patch_result(version, result: PatchResult, ext: str, changes: list) -> None:
    """
    패치 결과를 DB와 storage에 반영한다.

    - failed_items에 해당하는 DocumentChange.status를 FAILED로 갱신
    - applied_ids가 비어있으면 version.status = FAILED
    - applied_ids가 있으면:
        artifact_file을 storage에 저장 (인프라 경계 — try/except 격리)
        version.applied_change_ids, version.status = READY 갱신
    """
    from django.core.files.base import ContentFile
    from .models import DocumentChange, DocumentVersion

    # failed_items에 해당하는 change 상태를 FAILED로 갱신
    failed_op_ids = {item["operation_id"] for item in result.failed_items}
    for change in changes:
        if change.operation_id in failed_op_ids:
            change.status = DocumentChange.Status.FAILED
            change.save(update_fields=["status", "updated_at"])

    if not result.applied_ids:
        # failed_items에 구체적 실패 사유가 있으면 그것을 error_message로 사용한다.
        # 없으면 generic 메시지를 쓴다(예: changes 자체가 없는 경우).
        if result.failed_items:
            reason = "; ".join(item["reason"] for item in result.failed_items)
        else:
            reason = "적용 가능한 변경 항목이 없습니다."
        _set_failed(version, reason)
        return

    # artifact_file 저장 — storage I/O 실패는 인프라 경계이므로 try/except로 격리
    try:
        version.artifact_file.save(
            f"v{version.pk}.{ext}",
            ContentFile(result.output_bytes),
            save=False,
        )
        version.artifact_format = ext
    except Exception as exc:
        logger.exception("persist_patch_result: artifact_file 저장 실패 | version_id=%s", version.pk)
        _set_failed(version, f"결과 파일 저장 실패: {exc}")
        return

    version.applied_change_ids = result.applied_ids
    version.status = DocumentVersion.Status.READY
    version.save(update_fields=["artifact_file", "artifact_format", "applied_change_ids", "status", "updated_at"])


# ── 내부 헬퍼 (render_pdf 전용) ──────────────────────────────────────────────

def _set_failed(version, error_message: str) -> None:
    """version 상태를 FAILED로 설정하고 에러 메시지를 저장한다."""
    from .models import DocumentVersion
    version.status = DocumentVersion.Status.FAILED
    version.error_message = error_message
    version.save(update_fields=["status", "error_message", "updated_at"])


def _resolve_pdf_rect(doc, anchor: dict):
    """
    anchor 딕셔너리에서 (0-based 페이지 인덱스, fitz.Rect)를 반환한다.

    pdf_bbox: page(1-based) → 0-based 변환, rect 딕셔너리 → fitz.Rect
    text_match: search_for()로 텍스트 위치 탐색, occurrence 번째 결과 반환
    반환 None: 텍스트 없음, 페이지 범위 초과, rect 정보 누락
    """
    import fitz

    anchor_type = anchor.get("type", "")

    if anchor_type == "pdf_bbox":
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
        page_hint = anchor.get("page")
        occurrence = max(1, anchor.get("occurrence", 1))

        if page_hint is not None:
            page_idx = int(page_hint) - 1
            pages_to_search = [(page_idx, doc[page_idx])] if 0 <= page_idx < len(doc) else []
        else:
            pages_to_search = [(i, doc[i]) for i in range(len(doc))]

        hit_count = 0
        for idx, page in pages_to_search:
            for r in page.search_for(target):
                hit_count += 1
                if hit_count == occurrence:
                    return (idx, r)

        return None

    return None


def _apply_pdf_annotate(page, rect, change) -> None:
    """지정 rect에 하이라이트 주석을 추가한다."""
    comment = change.replacement or getattr(change, "reason", "") or ""
    annot = page.add_highlight_annot(rect)
    annot.set_info(content=comment)
    annot.update()


def _apply_pdf_redact_overlay(page, rect, change) -> None:
    """
    지정 rect 영역을 흰색으로 가린 뒤 replacement 텍스트를 overlay로 삽입한다.

    CJK 문자 포함 시 "korea-s" 폰트, 순수 ASCII는 "helv" 폰트를 사용한다.
    (korea-s로 ASCII를 그리면 문자 사이에 불필요한 폭이 생겨 텍스트 추출 시
     공백이 끼는 부작용이 있으므로 ASCII는 helv를 유지한다)
    """
    page.add_redact_annot(rect, fill=(1, 1, 1))
    page.apply_redactions()

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
