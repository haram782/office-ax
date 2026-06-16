from __future__ import annotations

from pathlib import Path

from celery import shared_task
from celery.utils.log import get_task_logger

from masking.pii_masker import mask_pii
from llm import get_llm_client, AnalysisResult
from parsers.excel_parser import parse_excel
from parsers.pdf_parser import parse_pdf
from parsers.csv_parser import parse_csv
from parsers.docx_parser import parse_docx
from parsers.pptx_parser import parse_pptx
from parsers.hwp_parser import parse_hwp
from parsers.image_parser import parse_image
from prompts.document_analysis import DOCUMENT_ANALYSIS_PROMPT

logger = get_task_logger(__name__)

_OCR_TEXT_THRESHOLD = 50  # 이 글자 수 미만이면 스캔 PDF로 판정

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

        output = {
            "upload_id":    upload_id,
            "summary":      result.summary,
            "errors":       result.detected_errors,
            "model_used":   result.model_used,
            "tokens":       {"input": result.input_tokens, "output": result.output_tokens},
            "pii_redacted": pii_counts,
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
        }

        # ── 5. 콜백 라우팅 ────────────────────────────────────────────────
        if chat_message_id is not None:
            self.app.send_task(
                "chat.notify_chat_response",
                kwargs={"chat_message_id": chat_message_id, "result": output},
                queue="celery",
            )
        else:
            self.app.send_task(
                "documents.notify_analysis_complete",
                kwargs={"upload_id": upload_id, "result": output},
                queue="celery",
            )

        return output

    except Exception as exc:
        logger.error("analyze_document 실패 | upload_id=%s | error=%s", upload_id, exc)
        raise self.retry(exc=exc)
