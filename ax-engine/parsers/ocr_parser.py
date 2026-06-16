"""
OCR 파서 — 스캔 PDF / 이미지에서 텍스트 추출.

3단계 파이프라인:
  1. [이미지 로딩]   PDF → 페이지별 이미지 (pdf2image + poppler)
  2. [전처리]        OpenCV: 그레이스케일 → 이진화(Otsu) → 노이즈 제거
  3. [OCR 추출]      EasyOCR (ko + en, GPU 선택)

현재 상태: 뼈대 코드. 패키지 미설치 시 fallback 메시지 반환.
운영 전환 전 설치: pip install easyocr opencv-python-headless pdf2image
                   + brew install poppler  (macOS)
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def ocr_extract(file_path: Path) -> tuple[str, dict]:
    """
    스캔 PDF 또는 이미지에서 텍스트를 추출한다.
    Returns: (text, meta)  meta = {"pages": int, "ocr_engine": str}
    """
    images = _load_images(file_path)
    if not images:
        return "", {"pages": 0, "ocr_engine": "none"}

    preprocessed = [_preprocess(img) for img in images]
    text_blocks = _run_ocr(preprocessed)

    return "\n\n".join(text_blocks), {
        "pages": len(images),
        "ocr_engine": _engine_name(),
    }


# ── 이미지 로딩 ───────────────────────────────────────────────────────────────

def _load_images(file_path: Path) -> list:
    suffix = file_path.suffix.lower()
    try:
        if suffix == ".pdf":
            return _pdf_to_images(file_path)
        return _load_image_file(file_path)
    except Exception as exc:
        logger.warning("이미지 로딩 실패 | file=%s | error=%s", file_path, exc)
        return []


def _pdf_to_images(file_path: Path) -> list:
    try:
        from pdf2image import convert_from_path
        return convert_from_path(str(file_path), dpi=200)
    except ImportError:
        logger.warning("pdf2image 미설치 — brew install poppler && pip install pdf2image")
        return []


def _load_image_file(file_path: Path) -> list:
    try:
        import cv2
        img = cv2.imread(str(file_path))
        return [img] if img is not None else []
    except ImportError:
        logger.warning("opencv 미설치 — pip install opencv-python-headless")
        return []


# ── OpenCV 전처리 ─────────────────────────────────────────────────────────────

def _preprocess(image):
    """
    그레이스케일 → Otsu 이진화 → fastNlMeansDenoising 순으로 처리.
    OpenCV 미설치 시 원본 반환.
    """
    try:
        import cv2
        import numpy as np

        # PIL Image(pdf2image 결과) → numpy array
        if not isinstance(image, np.ndarray):
            image = np.array(image)

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        _, binarized = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        denoised = cv2.fastNlMeansDenoising(binarized, h=10)
        return denoised

    except ImportError:
        return image


# ── EasyOCR ───────────────────────────────────────────────────────────────────

def _run_ocr(images: list) -> list[str]:
    try:
        import easyocr
        reader = easyocr.Reader(["ko", "en"], gpu=False)
        results = []
        for img in images:
            raw = reader.readtext(img, detail=0, paragraph=True)
            results.append(" ".join(raw))
        return results
    except ImportError:
        logger.warning("EasyOCR 미설치 — pip install easyocr")
        return ["[OCR_UNAVAILABLE: EasyOCR을 설치하면 스캔 문서 텍스트 추출이 가능합니다]"]


def _engine_name() -> str:
    try:
        import easyocr  # noqa: F401
        return "easyocr"
    except ImportError:
        return "fallback"
