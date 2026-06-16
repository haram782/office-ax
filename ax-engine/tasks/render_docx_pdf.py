"""
LibreOffice CLI 기반 DOCX → 페이지별 PNG 렌더링.

파이프라인: DOCX → PDF (LibreOffice) → 페이지별 PNG (pdftoppm)

환경 변수:
  DOCX_PDF_DIR    — 변환 결과를 저장할 루트 경로
  ARTIFACT_DIR    — 공유 아티팩트 루트 (DOCX_PDF_DIR 기본값 계산에 사용)
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
DOCX_PDF_DIR = Path(os.getenv("DOCX_PDF_DIR", str(_ARTIFACT_DIR.parent / "docx_pdf")))


def render_docx_to_pages(docx_path: Path, upload_id: int) -> list[str]:
    """
    DOCX → 페이지별 PNG 변환.

    Returns:
        list of "/media/docx_pdf/{upload_id}/page_N.png" URL strings
    Raises:
        RuntimeError — LibreOffice/pdftoppm 미설치 또는 변환 실패
    """
    out_dir = DOCX_PDF_DIR / str(upload_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)

        # 1단계: DOCX → PDF
        pdf_path = _docx_to_pdf(docx_path, tmp_dir)

        # 2단계: PDF → 페이지별 PNG
        _pdf_to_pngs(pdf_path, tmp_dir)

        raw = sorted(tmp_dir.glob("page-*.png"), key=_sort_key)
        if not raw:
            raise RuntimeError(
                "페이지 PNG 생성 실패 — pdftoppm 설치 여부 확인\n"
                "  macOS: brew install poppler"
            )

        urls: list[str] = []
        for i, f in enumerate(raw, 1):
            target = out_dir / f"page_{i}.png"
            f.rename(target)
            urls.append(f"/media/docx_pdf/{upload_id}/page_{i}.png")

    return urls


def _docx_to_pdf(docx_path: Path, out_dir: Path) -> Path:
    result = subprocess.run(
        [
            _lo_binary(), "--headless", "--norestore",
            "--convert-to", "pdf:writer_pdf_Export",
            "--outdir", str(out_dir),
            str(docx_path),
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
        [_pdftoppm_binary(), "-r", "150", "-png", str(pdf_path), str(out_dir / "page")],
        capture_output=True,
        timeout=120,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace")[:400]
        raise RuntimeError(f"pdftoppm 오류 (code {result.returncode}): {stderr}")


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
        "  macOS: brew install poppler"
    )


def _sort_key(p: Path) -> int:
    m = re.search(r"(\d+)$", p.stem)
    return int(m.group(1)) if m else 0
