from __future__ import annotations

from pathlib import Path

from celery import shared_task
from celery.utils.log import get_task_logger

from masking.pii_masker import mask_pii
from llm import get_llm_client, AnalysisResult
from parsers.excel_parser import extract_sheet_preview, parse_excel
from parsers.pdf_parser import parse_pdf
from parsers.csv_parser import parse_csv
from parsers.docx_parser import parse_docx
from parsers.pptx_parser import parse_pptx
from parsers.hwp_parser import parse_hwp
from parsers.image_parser import parse_image
from prompts.document_analysis import DOCUMENT_ANALYSIS_PROMPT

logger = get_task_logger(__name__)

_OCR_TEXT_THRESHOLD = 50  # 이 글자 수 미만이면 스캔 PDF로 판정
_PATCH_CONTEXT_TEXT_LIMIT = 20000

# suffix → (parser_fn, source_type)
# source_type 값은 UserActionLog.FileType 값과 일치시킨다
_SUFFIX_DISPATCH: dict[str, tuple] = {
    ".xlsx":  (parse_excel, "xlsx"),
    ".xls":   (parse_excel, "xlsx"),
    ".csv":   (parse_csv,   "csv"),
    ".pdf":   (parse_pdf,   None),   # pdf는 하위에서 digital/image 판별
    ".docx":  (parse_docx,  "docx"),
    ".doc":   (parse_docx,  "docx"),
    ".pptx":  (parse_pptx,  "pptx"),
    ".hwp":   (parse_hwp,   "hwp"),
    ".hwpx":  (parse_hwp,   "hwp"),
    ".png":   (parse_image, "image"),
    ".jpg":   (parse_image, "image"),
    ".jpeg":  (parse_image, "image"),
    ".webp":  (parse_image, "image"),
    ".gif":   (parse_image, "image"),
}

_ACTION_TAGS: dict[str, str] = {
    "xlsx":        "#수식_보정",
    "csv":         "#데이터_분석",
    "pdf_digital": "#문서_분석",
    "pdf_image":   "#OCR_추출",
    "docx":        "#문서_교정",
    "pptx":        "#발표자료_검토",
    "hwp":         "#문서_교정",
    "image":       "#OCR_추출",
}

# 스캔본·이미지 안내 문구 — OCR 미구현 동안 사용자에게 정직하게 알린다
# (closed-beta-launch-plan-v1-ko.md 갭 6: 베타 제외 + 정직한 안내)
_SCAN_UNSUPPORTED_SUMMARY = (
    "스캔 문서(이미지 기반)는 아직 지원하지 않아요. "
    "텍스트가 포함된 원본 파일(디지털 PDF, XLSX, DOCX, HWP)을 올려주시면 분석할 수 있어요."
)


def _unsupported_scan_output(upload_id: int, source_type: str) -> dict:
    """
    스캔본·이미지 문서의 안내 결과를 만든다.

    LLM을 호출하지 않으므로 usage는 전부 0/unavailable.
    크레딧 차감 제외는 백엔드가 source_type을 보고 FAILED로 기록하는 것으로
    보장한다 (backend services/usage.analysis_status_for_result 참조).
    """
    return {
        "upload_id":    upload_id,
        "summary":      _SCAN_UNSUPPORTED_SUMMARY,
        "errors":       [],
        "model_used":   "",
        "tokens":       {"input": 0, "output": 0},
        "usage":        {"input_tokens": 0, "output_tokens": 0, "token_source": "unavailable"},
        "model":        "",
        "provider":     "",
        "pii_redacted": {},
        "source_type":  source_type,
        "action_tag":   _ACTION_TAGS.get(source_type, "#문서_분석"),
        "artifact_url": "",
        "slide_urls":   [],
        "slide_count":  0,
        "docx_page_urls":  [],
        "docx_page_count": 0,
        "pptx_structured": [],
    }


def _patch_context_text(text: str) -> str:
    """PatchPlan 생성에 사용할 마스킹된 본문 스냅샷을 제한 길이로 보관한다."""
    return (text or "")[:_PATCH_CONTEXT_TEXT_LIMIT]


def _route_callback(task_self, chat_message_id: int | None, upload_id: int, output: dict) -> None:
    """분석 결과를 채팅/레거시 플로우에 맞는 Django 콜백 태스크로 전달한다."""
    if chat_message_id is not None:
        task_self.app.send_task(
            "chat.notify_chat_response",
            kwargs={"chat_message_id": chat_message_id, "result": output},
            queue="celery",
        )
    else:
        task_self.app.send_task(
            "documents.notify_analysis_complete",
            kwargs={"upload_id": upload_id, "result": output},
            queue="celery",
        )


@shared_task(bind=True, name="tasks.analyze_document", max_retries=3, default_retry_delay=30)
def analyze_document(
    self,
    file_path: str,
    upload_id: int,
    chat_message_id: int | None = None,
) -> dict:
    """
    Django 백엔드가 호출하는 진입점.

    chat_message_id 유무에 따라 콜백 라우팅 분기:
      - 있음 → chat.notify_chat_response  (채팅 워크스페이스 플로우)
      - 없음 → documents.notify_analysis_complete  (레거시 단방향 업로드 플로우)
    """
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix not in _SUFFIX_DISPATCH:
        raise ValueError(f"지원하지 않는 파일 형식: {suffix}")

    try:
        # ── 1. 파일 타입별 텍스트 추출 ──────────────────────────────────────
        parser_fn, source_type = _SUFFIX_DISPATCH[suffix]
        raw_text, meta = parser_fn(path)

        # PDF만 디지털/스캔 이미지 여부 추가 판별
        if suffix == ".pdf":
            if len(raw_text.strip()) < _OCR_TEXT_THRESHOLD:
                source_type = "pdf_image"
                logger.info("스캔 PDF 감지 → OCR 파이프라인 | upload_id=%s", upload_id)
                from parsers.ocr_parser import ocr_extract
                ocr_text, ocr_meta = ocr_extract(path)
                raw_text = ocr_text or raw_text
                meta.update(ocr_meta)
            else:
                source_type = "pdf_digital"

        logger.info("텍스트 추출 완료 | upload_id=%s | source_type=%s", upload_id, source_type)

        # 스캔본·이미지는 OCR 미구현으로 베타에서 지원하지 않는다.
        # LLM 호출 전에 안내로 종료해 "무한 분석 중"이나 깨진 분석 결과를 방지한다.
        if source_type in ("pdf_image", "image"):
            logger.info("스캔본·이미지 미지원 안내 반환 | upload_id=%s | source_type=%s", upload_id, source_type)
            output = _unsupported_scan_output(upload_id, source_type)
            _route_callback(self, chat_message_id, upload_id, output)
            return output

        # ── 2. PII 마스킹 ────────────────────────────────────────────────────
        masked_text, pii_counts = mask_pii(raw_text)
        if pii_counts:
            logger.info("PII 마스킹 완료 | upload_id=%s | %s", upload_id, pii_counts)

        # ── 3. LLM 분석 ──────────────────────────────────────────────────────
        client = get_llm_client()
        result: AnalysisResult = client.analyze(
            masked_text,
            DOCUMENT_ANALYSIS_PROMPT,
            source_type=source_type,
            upload_id=upload_id,
            file_path=str(path),  # GeminiClient가 멀티모달 경로에서 활용, 기존 클라이언트는 무시
        )

        # ── 4. artifact_path → 서빙 URL 변환 ────────────────────────────────
        artifact_url = ""
        if result.artifact_path:
            artifact_url = f"/media/artifacts/{Path(result.artifact_path).name}"

        # ── 4-b. PPTX: 슬라이드 이미지 렌더링 (LibreOffice) ─────────────────
        slide_urls: list[str] = []
        if source_type == "pptx":
            try:
                from tasks.render_pptx_slides import render_pptx_to_images
                slide_urls = render_pptx_to_images(path, upload_id)
                logger.info(
                    "PPTX 슬라이드 렌더링 완료 | upload_id=%s | slides=%d",
                    upload_id, len(slide_urls),
                )
            except Exception as render_err:
                logger.warning(
                    "PPTX 슬라이드 렌더링 실패 (LibreOffice 미설치?): %s", render_err
                )

        # ── 4-c. DOCX: 페이지별 PNG 렌더링 (LibreOffice + pdftoppm) ───────────
        docx_page_urls: list[str] = []
        if source_type == "docx":
            try:
                from tasks.render_docx_pdf import render_docx_to_pages
                docx_page_urls = render_docx_to_pages(path, upload_id)
                logger.info(
                    "DOCX 페이지 렌더링 완료 | upload_id=%s | pages=%d",
                    upload_id, len(docx_page_urls),
                )
            except Exception as render_err:
                logger.warning(
                    "DOCX 페이지 렌더링 실패 (LibreOffice/pdftoppm 미설치?): %s", render_err
                )

        # ── 4-d. XLSX: 최초 분석 단계에서도 "시트 미리보기" 표를 채울 실제
        # headers/preview_rows를 추출한다. patch 적용 전(artifact 없음)에도
        # 뷰어에 원본 시트 내용이 보이게 하기 위함이다.
        snippet_data: dict = {}
        if source_type == "xlsx":
            try:
                preview = extract_sheet_preview(path)
                snippet_data = {"type": "excel_preview", **preview}
            except Exception as preview_err:
                logger.warning(
                    "XLSX 시트 미리보기 추출 실패 | upload_id=%s | %s", upload_id, preview_err
                )

        output = {
            "upload_id":    upload_id,
            "summary":      result.summary,
            "errors":       result.detected_errors,
            # 하위 호환용 — 신규 소비자는 usage/model/provider를 사용한다
            "model_used":   result.model_used,
            "tokens":       {"input": result.input_tokens, "output": result.output_tokens},
            # backend usage_metadata_from_result()가 UsageEvent 기록에 사용하는 계약 키
            "usage": {
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "token_source": result.token_source,
            },
            "model":        result.model_used,
            "provider":     result.provider,
            "pii_redacted": pii_counts,
            "document_text": _patch_context_text(masked_text),
            "source_type":  source_type,
            "action_tag":   _ACTION_TAGS.get(source_type, "#문서_분석"),
            "artifact_url": artifact_url,
            # PPTX 전용 — 빈 리스트이면 프론트엔드는 LibreOffice 미설치 안내 표시
            "slide_urls":   slide_urls,
            "slide_count":  len(slide_urls),
            # DOCX 전용 — 빈 리스트이면 프론트엔드는 LibreOffice 미설치 안내 표시
            "docx_page_urls":  docx_page_urls,
            "docx_page_count": len(docx_page_urls),
            # AI 패치 엔진용 구조화 데이터 (source_type == "pptx" 일 때만 채워짐)
            "pptx_structured": meta.get("structured", []) if source_type == "pptx" else [],
            # XLSX 전용 — "시트 미리보기" 표. 빈 dict이면 백엔드가 fallback 데모로 대체
            "snippet_data": snippet_data,
        }

        # ── 5. 콜백 라우팅 ────────────────────────────────────────────────
        _route_callback(self, chat_message_id, upload_id, output)

        return output

    except Exception as exc:
        logger.error("analyze_document 실패 | upload_id=%s | error=%s", upload_id, exc)
        raise self.retry(exc=exc)
