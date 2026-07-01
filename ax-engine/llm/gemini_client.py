"""
GeminiClient: gemini CLI subprocess를 사용하는 LLM 클라이언트.

환경변수:
  GEMINI_MODEL   — 사용할 Gemini 모델명 (기본: gemini-2.0-flash)
  GEMINI_TIMEOUT — subprocess 타임아웃 초 (기본: 120)
"""
import json
import logging
import os
import re
import subprocess

from .base import BaseLLMClient, AnalysisResult

logger = logging.getLogger(__name__)

# 마크다운 코드펜스 또는 순수 JSON 객체를 추출하는 정규식
_JSON_BLOCK_RE = re.compile(
    r"```(?:json)?\s*([\s\S]+?)\s*```|(\{[\s\S]+\})",
    re.DOTALL,
)

# 멀티모달 경로가 필요한 source_type
_MULTIMODAL_SOURCE_TYPES = {"image", "pdf_image"}

# JSON만 반환하도록 CLI에 강제하는 지시문
_JSON_ONLY_INSTRUCTION = (
    "\n\n반드시 유효한 JSON만 반환하라. "
    "마크다운, 설명, 코드펜스 없이 JSON 객체만 출력하라."
)


class GeminiClient(BaseLLMClient):
    """
    gemini CLI를 subprocess로 호출하는 LLM 클라이언트.
    텍스트 전용 경로와 이미지/PDF 멀티모달 경로를 모두 지원한다.
    """

    def __init__(self) -> None:
        self._model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
        self._timeout = int(os.environ.get("GEMINI_TIMEOUT", "120"))

    def analyze(self, masked_text: str, system_prompt: str, **context) -> AnalysisResult:
        prompt = system_prompt + "\n\n" + masked_text + _JSON_ONLY_INSTRUCTION

        cmd = self._build_cmd(context, prompt)
        stdout = self._run_cli(cmd)
        parsed = self._extract_json(stdout)

        return AnalysisResult(
            summary=parsed.get("summary", parsed.get("reply", "")),
            detected_errors=parsed.get("errors", []),
            model_used=f"gemini/{self._model}",
            parsed_data=parsed,
        )

    # ── 내부 헬퍼 ──────────────────────────────────────────────────────────────

    def _build_cmd(self, context: dict, prompt: str) -> list[str]:
        """source_type과 file_path에 따라 CLI 명령어를 조립한다."""
        source_type = context.get("source_type", "")
        file_path = context.get("file_path", "")
        # 이미지/스캔PDF인 경우 파일 경로를 인자로 추가해 멀티모달 처리
        if file_path and source_type in _MULTIMODAL_SOURCE_TYPES:
            return ["gemini", file_path, "-p", prompt]
        # 텍스트 전용: -p 플래그로 headless 모드 실행
        return ["gemini", "-p", prompt]

    def _run_cli(self, cmd: list[str]) -> str:
        """subprocess로 gemini CLI를 실행하고 stdout을 반환한다."""
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except FileNotFoundError as e:
            raise EnvironmentError(
                "gemini CLI를 찾을 수 없습니다. "
                "설치 안내: npm install -g @google/generative-ai 또는 "
                "https://ai.google.dev/gemini-api/docs/gemini-cli 참조"
            ) from e
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(
                f"gemini CLI 타임아웃 ({self._timeout}초) — 모델: {self._model}"
            ) from e

        if proc.returncode != 0:
            raise RuntimeError(
                f"gemini CLI 오류 (returncode={proc.returncode}): {proc.stderr.strip()}"
            )

        return proc.stdout.strip()

    def _extract_json(self, stdout: str) -> dict:
        """stdout에서 JSON 블록을 추출하고 파싱한다."""
        match = _JSON_BLOCK_RE.search(stdout)
        if match:
            # 코드펜스 내부 또는 순수 JSON 객체 중 매칭된 그룹 선택
            json_str = match.group(1) or match.group(2)
        else:
            json_str = stdout

        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error("gemini CLI JSON 파싱 실패 | stdout=%s", stdout)
            raise RuntimeError(f"gemini CLI 응답 JSON 파싱 실패: {e}") from e
