"""
ClaudeCodeCLIClient: claude CLI subprocess를 사용하는 LLM 클라이언트.

로컬 개발/테스트 전용. 프로덕션에서는 AnthropicClient(API 키)를 사용한다.
Claude Code Pro 플랜 구독으로 추가 과금 없이 사용 가능하다.

환경변수:
  CLAUDE_CLI_TIMEOUT — subprocess 타임아웃 초 (기본: 120)
  CLAUDE_CLI_MODEL   — model_used 필드에 표시할 모델명 (기본: claude-cli)
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

# JSON만 반환하도록 강제하는 지시문
_JSON_ONLY_INSTRUCTION = (
    "\n\n반드시 유효한 JSON만 반환하라. "
    "마크다운, 설명, 코드펜스 없이 JSON 객체만 출력하라."
)


class ClaudeCodeCLIClient(BaseLLMClient):
    """
    claude CLI를 subprocess로 호출하는 LLM 클라이언트.
    로컬 Claude Code Pro 플랜을 활용해 API 과금 없이 사용한다.
    """

    def __init__(self) -> None:
        self._timeout = int(os.environ.get("CLAUDE_CLI_TIMEOUT", "120"))
        self._model_label = os.environ.get("CLAUDE_CLI_MODEL", "claude-cli")

    def analyze(self, masked_text: str, system_prompt: str, **context) -> AnalysisResult:
        prompt = system_prompt + "\n\n" + masked_text + _JSON_ONLY_INSTRUCTION

        cmd = ["claude", "-p", prompt]
        stdout = self._run_cli(cmd)
        parsed = self._extract_json(stdout)

        return AnalysisResult(
            summary=parsed.get("summary", parsed.get("reply", "")),
            detected_errors=parsed.get("errors", []),
            model_used=f"claude-cli/{self._model_label}",
            parsed_data=parsed,
        )

    def _run_cli(self, cmd: list[str]) -> str:
        """subprocess로 claude CLI를 실행하고 stdout을 반환한다."""
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except FileNotFoundError as e:
            raise EnvironmentError(
                "claude CLI를 찾을 수 없습니다. "
                "Claude Code가 설치돼 있는지 확인하세요: https://claude.ai/code"
            ) from e
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(
                f"claude CLI 타임아웃 ({self._timeout}초)"
            ) from e

        if proc.returncode != 0:
            raise RuntimeError(
                f"claude CLI 오류 (returncode={proc.returncode}): {proc.stderr.strip()}"
            )

        return proc.stdout.strip()

    def _extract_json(self, stdout: str) -> dict:
        """stdout에서 JSON 블록을 추출하고 파싱한다."""
        match = _JSON_BLOCK_RE.search(stdout)
        if match:
            json_str = match.group(1) or match.group(2)
        else:
            json_str = stdout

        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error("claude CLI JSON 파싱 실패 | stdout=%s", stdout)
            raise RuntimeError(f"claude CLI 응답 JSON 파싱 실패: {e}") from e
