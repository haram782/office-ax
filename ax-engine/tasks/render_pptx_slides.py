"""
LibreOffice CLI 기반 PPTX → per-slide PNG 렌더링 유틸리티.

파이프라인: PPTX → PDF (LibreOffice) → 슬라이드별 PNG (pdftoppm)

환경 변수:
  SLIDE_DIR      — 슬라이드 PNG를 저장할 루트 경로
  ARTIFACT_DIR   — llm/mock_client.py 와 공유하는 아티팩트 루트
  LIBREOFFICE_BIN — LibreOffice 실행 파일 경로 (미설정 시 자동 탐색)
  PDFTOPPM_BIN   — pdftoppm 실행 파일 경로 (미설정 시 자동 탐색)
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

_ARTIFACT_DIR = Path(os.getenv("ARTIFACT_DIR", "/tmp/ax-artifacts"))
SLIDE_DIR = Path(os.getenv("SLIDE_DIR", str(_ARTIFACT_DIR.parent / "slides")))


def render_pptx_to_images(pptx_path: Path, upload_id: int) -> list[str]:
    """
    PPTX 전체 슬라이드 → PNG 일괄 변환.

    Returns:
        list of "/media/slides/{upload_id}/slide_N.png" URL strings
    Raises:
        RuntimeError — LibreOffice/pdftoppm 미설치 또는 변환 실패
    """
    out_dir = SLIDE_DIR / str(upload_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)

        # 1단계: PPTX → PDF
        pdf_path = _pptx_to_pdf(pptx_path, tmp_dir)

        # 2단계: PDF → 슬라이드별 PNG
        _pdf_to_pngs(pdf_path, tmp_dir)

        raw_files = sorted(tmp_dir.glob("slide-*.png"), key=_slide_sort_key)
        if not raw_files:
            raise RuntimeError(
                "슬라이드 PNG 생성 실패 — pdftoppm 설치 여부 확인\n"
                "  macOS: brew install poppler"
            )

        urls: list[str] = []
        for i, f in enumerate(raw_files, 1):
            target = out_dir / f"slide_{i}.png"
            f.rename(target)
            urls.append(f"/media/slides/{upload_id}/slide_{i}.png")

    return urls


def render_single_slide_image(pptx_path: Path, upload_id: int, slide_index: int) -> str:
    """
    Patch 후 단일 슬라이드 재렌더링.

    Returns:
        캐시 버스팅 URL: "/media/slides/{upload_id}/slide_{n}.png?v={timestamp}"
    """
    import time

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        pdf_path = _pptx_to_pdf(pptx_path, tmp_dir)
        _pdf_to_pngs(pdf_path, tmp_dir)
        raw_files = sorted(tmp_dir.glob("slide-*.png"), key=_slide_sort_key)

        if slide_index >= len(raw_files):
            raise ValueError(
                f"슬라이드 인덱스 {slide_index} 범위 초과 (총 {len(raw_files)}장)"
            )

        target_dir = SLIDE_DIR / str(upload_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"slide_{slide_index + 1}.png"
        raw_files[slide_index].replace(target)

    v = int(time.time())
    return f"/media/slides/{upload_id}/slide_{slide_index + 1}.png?v={v}"


# ── 내부 유틸 ──────────────────────────────────────────────────────────────────

def _pptx_to_pdf(pptx_path: Path, out_dir: Path) -> Path:
    """PPTX → PDF 변환. 생성된 PDF 경로 반환."""
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
    """PDF → 슬라이드별 PNG. out_dir/slide-NNNN.png 형태로 생성."""
    result = subprocess.run(
        [
            _pdftoppm_binary(),
            "-r", "150",      # 150 DPI
            "-png",
            str(pdf_path),
            str(out_dir / "slide"),
        ],
        capture_output=True,
        timeout=120,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace")[:400]
        raise RuntimeError(f"pdftoppm PNG 변환 오류 (code {result.returncode}): {stderr}")


def _lo_binary() -> str:
    if env_bin := os.getenv("LIBREOFFICE_BIN"):
        return env_bin
    import shutil
    if found := shutil.which("libreoffice") or shutil.which("soffice"):
        return found
    mac_path = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
    if Path(mac_path).exists():
        return mac_path
    raise RuntimeError(
        "LibreOffice를 찾을 수 없습니다.\n"
        "  macOS: brew install --cask libreoffice\n"
        "  Ubuntu: apt install libreoffice\n"
        "또는 LIBREOFFICE_BIN 환경변수로 경로를 직접 지정하세요."
    )


def _pdftoppm_binary() -> str:
    if env_bin := os.getenv("PDFTOPPM_BIN"):
        return env_bin
    import shutil
    if found := shutil.which("pdftoppm"):
        return found
    raise RuntimeError(
        "pdftoppm를 찾을 수 없습니다.\n"
        "  macOS: brew install poppler\n"
        "  Ubuntu: apt install poppler-utils"
    )


def _slide_sort_key(p: Path) -> int:
    """pdftoppm 출력 파일명(slide-1.png, slide-01.png 등) 숫자 정렬."""
    m = re.search(r"(\d+)$", p.stem)
    return int(m.group(1)) if m else 0
