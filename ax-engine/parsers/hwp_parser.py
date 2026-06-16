"""
HWP / HWPX 파서.

• .hwpx  ZIP+XML 구조 → stdlib만으로 파싱
• .hwp   독점 바이너리 → pyhwp(hwp5) CLI 시도 → olefile fallback → 텍스트 없음
"""
from __future__ import annotations

import logging
import re
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)


def parse_hwp(file_path: str | Path) -> tuple[str, dict]:
    """Returns (text_content, meta)."""
    path = Path(file_path)
    if path.suffix.lower() == ".hwpx":
        return _parse_hwpx(path)
    return _parse_hwp_binary(path)


# ── HWPX (ZIP+XML) ────────────────────────────────────────────────────────────

def _parse_hwpx(path: Path) -> tuple[str, dict]:
    try:
        texts: list[str] = []
        with zipfile.ZipFile(path, "r") as zf:
            for name in sorted(zf.namelist()):
                # 본문 섹션 XML: Contents/Sections/Section0.xml 등
                if re.match(r"Contents/Sections/Section\d+\.xml", name):
                    raw = zf.read(name)
                    # XML 태그 제거 후 텍스트만 남김
                    text = re.sub(rb"<[^>]+>", b" ", raw).decode("utf-8", errors="ignore")
                    text = re.sub(r"\s+", " ", text).strip()
                    if text:
                        texts.append(text)

        return "\n\n".join(texts) or "[빈 문서]", {"format": "hwpx"}

    except Exception as exc:
        logger.warning("HWPX 파싱 실패 | file=%s | %s", path, exc)
        return "[HWPX_PARSE_ERROR]", {}


# ── HWP 바이너리 ──────────────────────────────────────────────────────────────

def _parse_hwp_binary(path: Path) -> tuple[str, dict]:
    # 1차 시도: pyhwp (패키지명 hwp5) CLI
    text = _try_pyhwp(path)
    if text:
        return text, {"format": "hwp", "method": "pyhwp"}

    # 2차 시도: olefile로 BodyText/Section0 스트림 직접 읽기
    text = _try_olefile(path)
    if text:
        return text, {"format": "hwp", "method": "olefile"}

    logger.warning("HWP 텍스트 추출 실패 | file=%s | pip install pyhwp olefile 권장", path)
    return (
        f"[HWP_TEXT_UNAVAILABLE]\n파일명: {path.name}\n"
        "pyhwp 또는 olefile 패키지를 설치하면 내용 추출이 가능합니다.",
        {"format": "hwp", "method": "none"},
    )


def _try_pyhwp(path: Path) -> str:
    try:
        import subprocess, sys
        result = subprocess.run(
            [sys.executable, "-m", "hwp5.hwp5txt", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""


def _try_olefile(path: Path) -> str:
    try:
        import olefile
        with olefile.OleFileIO(str(path)) as ole:
            if ole.exists("BodyText/Section0"):
                raw = ole.openstream("BodyText/Section0").read()
                text = raw.decode("utf-16-le", errors="ignore")
                # 제어 문자 제거
                text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]", " ", text)
                return re.sub(r"\s+", " ", text).strip()
    except Exception:
        pass
    return ""
