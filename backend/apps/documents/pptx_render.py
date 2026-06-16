"""
Django 백엔드에서 직접 실행하는 LibreOffice 기반 PPTX 슬라이드 렌더러.
PptxPatchView 에서 python-pptx 패치 후 단일 슬라이드 재렌더링에 사용한다.

파이프라인: PPTX → PDF (LibreOffice) → 슬라이드별 PNG (pdftoppm)
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings

SLIDE_ROOT = Path(settings.MEDIA_ROOT) / "slides"


def render_all_slides(pptx_path: Path, upload_id: int) -> list[str]:
    """전체 슬라이드 PNG 변환. /media/slides/{upload_id}/slide_N.png URL 목록 반환."""
    out_dir = SLIDE_ROOT / str(upload_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        pdf_path = _pptx_to_pdf(pptx_path, tmp_dir)
        _pdf_to_pngs(pdf_path, tmp_dir)

        raw = sorted(tmp_dir.glob("slide-*.png"), key=_sort_key)
        if not raw:
            raise RuntimeError(
                "슬라이드 PNG 생성 실패 — pdftoppm 설치 여부 확인\n"
                "  macOS: brew install poppler"
            )

        urls: list[str] = []
        for i, f in enumerate(raw, 1):
            target = out_dir / f"slide_{i}.png"
            f.rename(target)
            urls.append(f"/media/slides/{upload_id}/slide_{i}.png")

    return urls


def render_one_slide(pptx_path: Path, upload_id: int, slide_index: int) -> str:
    """
    단일 슬라이드 재렌더링.
    캐시 버스팅 URL: /media/slides/{upload_id}/slide_{n}.png?v={timestamp}
    """
    import time

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        pdf_path = _pptx_to_pdf(pptx_path, tmp_dir)
        _pdf_to_pngs(pdf_path, tmp_dir)
        raw = sorted(tmp_dir.glob("slide-*.png"), key=_sort_key)

        if slide_index >= len(raw):
            raise ValueError(f"slide_index={slide_index} 범위 초과 (총 {len(raw)}장)")

        target_dir = SLIDE_ROOT / str(upload_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"slide_{slide_index + 1}.png"
        raw[slide_index].replace(target)

    v = int(time.time())
    return f"/media/slides/{upload_id}/slide_{slide_index + 1}.png?v={v}"


def _pptx_to_pdf(pptx_path: Path, out_dir: Path) -> Path:
    result = subprocess.run(
        [
            _lo_binary(), "--headless", "--norestore",
            "--convert-to", "pdf:impress_pdf_Export",
            "--outdir", str(out_dir),
            str(pptx_path),
        ],
        capture_output=True,
        timeout=120,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace")[:400]
        raise RuntimeError(f"LibreOffice PDF 변환 오류 (code {result.returncode}): {stderr}")
    pdfs = list(out_dir.glob("*.pdf"))
    if not pdfs:
        raise RuntimeError("LibreOffice PDF 변환 결과 없음")
    return pdfs[0]


def _pdf_to_pngs(pdf_path: Path, out_dir: Path) -> None:
    result = subprocess.run(
        [_pdftoppm_binary(), "-r", "150", "-png", str(pdf_path), str(out_dir / "slide")],
        capture_output=True,
        timeout=120,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace")[:400]
        raise RuntimeError(f"pdftoppm 오류 (code {result.returncode}): {stderr}")


def _lo_binary() -> str:
    import shutil
    if env_bin := os.getenv("LIBREOFFICE_BIN"):
        return env_bin
    if found := shutil.which("libreoffice") or shutil.which("soffice"):
        return found
    mac_path = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
    if Path(mac_path).exists():
        return mac_path
    raise RuntimeError("LibreOffice 미설치 — brew install --cask libreoffice 또는 LIBREOFFICE_BIN 환경변수 설정")


def _pdftoppm_binary() -> str:
    import shutil
    if env_bin := os.getenv("PDFTOPPM_BIN"):
        return env_bin
    if found := shutil.which("pdftoppm"):
        return found
    raise RuntimeError("pdftoppm 미설치 — brew install poppler 또는 PDFTOPPM_BIN 환경변수 설정")


def _sort_key(p: Path) -> int:
    m = re.search(r"(\d+)$", p.stem)
    return int(m.group(1)) if m else 0
