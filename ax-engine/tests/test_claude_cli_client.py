"""
ClaudeCodeCLIClient 단위 테스트.

claude CLI subprocess를 mock 처리해 외부 의존 없이 검증한다.

커버 범위:
  1. 정상 호출 → AnalysisResult 반환
  2. CLI 미설치(FileNotFoundError) → EnvironmentError
  3. returncode != 0 → RuntimeError (stderr 포함)
  4. TimeoutExpired → RuntimeError
  5. JSON 파싱 실패 → RuntimeError
  6. 마크다운 코드펜스로 감싸인 JSON도 정상 파싱
  7. -p 인자에 system_prompt와 user 입력이 포함되는지 검증
  8. parsed_data에 전체 파싱 결과 보존
"""
import json
import subprocess
import sys
import os
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from llm.claude_cli_client import ClaudeCodeCLIClient


def _make_proc(stdout: str = "", stderr: str = "", returncode: int = 0) -> MagicMock:
    """subprocess.run 반환값 mock 생성 헬퍼."""
    proc = MagicMock()
    proc.stdout = stdout
    proc.stderr = stderr
    proc.returncode = returncode
    return proc


_VALID_JSON = json.dumps({
    "summary": "테스트 요약입니다.",
    "errors": ["오류1"],
})


class TestClaudeCodeCLIClientNormal(unittest.TestCase):
    """정상 동작 케이스."""

    @patch("subprocess.run")
    def test_returns_analysis_result(self, mock_run):
        """정상 JSON stdout → AnalysisResult 반환."""
        mock_run.return_value = _make_proc(stdout=_VALID_JSON)

        client = ClaudeCodeCLIClient()
        result = client.analyze("문서 내용", "시스템 프롬프트")

        self.assertEqual(result.summary, "테스트 요약입니다.")
        self.assertEqual(result.detected_errors, ["오류1"])
        self.assertTrue(result.model_used.startswith("claude-cli/"))

    @patch("subprocess.run")
    def test_provider_and_token_source_are_explicit(self, mock_run):
        """
        [버그 수정] provider/token_source를 명시하지 않으면 AnalysisResult
        dataclass의 위험한 기본값(provider="", token_source="provider_reported")을
        그대로 물려받는다. CLI subprocess는 실제 토큰 수를 알 수 없으므로
        token_source는 반드시 'unavailable'이어야 하고, provider도 'claude_cli'로
        명시해야 UsageEvent/대시보드에서 이 호출을 올바르게 식별할 수 있다.
        """
        mock_run.return_value = _make_proc(stdout=_VALID_JSON)

        client = ClaudeCodeCLIClient()
        result = client.analyze("문서 내용", "시스템 프롬프트")

        self.assertEqual(result.provider, "claude_cli")
        self.assertEqual(result.token_source, "unavailable")
        self.assertEqual(result.input_tokens, 0)
        self.assertEqual(result.output_tokens, 0)

    @patch("subprocess.run")
    def test_cmd_contains_system_and_user_prompt(self, mock_run):
        """CLI -p 인자에 system_prompt와 user 입력이 모두 포함된다."""
        mock_run.return_value = _make_proc(stdout=_VALID_JSON)

        client = ClaudeCodeCLIClient()
        client.analyze("사용자 입력", "시스템 지시")

        cmd = mock_run.call_args.args[0]
        prompt_arg = " ".join(cmd)
        self.assertIn("시스템 지시", prompt_arg)
        self.assertIn("사용자 입력", prompt_arg)
        self.assertIn("JSON", prompt_arg)

    @patch("subprocess.run")
    def test_fenced_json_parsed_correctly(self, mock_run):
        """마크다운 코드펜스로 감싸인 JSON도 정상 파싱한다."""
        fenced = f"```json\n{_VALID_JSON}\n```"
        mock_run.return_value = _make_proc(stdout=fenced)

        client = ClaudeCodeCLIClient()
        result = client.analyze("내용", "프롬프트")

        self.assertEqual(result.detected_errors, ["오류1"])

    @patch("subprocess.run")
    def test_parsed_data_preserved(self, mock_run):
        """parsed_data에 전체 파싱 결과가 보존된다."""
        full = json.dumps({"summary": "요약", "errors": [], "type": "qa", "reply": "답변"})
        mock_run.return_value = _make_proc(stdout=full)

        client = ClaudeCodeCLIClient()
        result = client.analyze("내용", "프롬프트")

        self.assertEqual(result.parsed_data.get("type"), "qa")
        self.assertEqual(result.parsed_data.get("reply"), "답변")


class TestClaudeCodeCLIClientErrors(unittest.TestCase):
    """에러 케이스."""

    @patch("subprocess.run", side_effect=FileNotFoundError("No such file"))
    def test_cli_not_installed_raises_environment_error(self, _mock_run):
        """claude CLI 미설치 시 EnvironmentError."""
        client = ClaudeCodeCLIClient()
        with self.assertRaises(EnvironmentError) as ctx:
            client.analyze("내용", "프롬프트")
        self.assertIn("claude", str(ctx.exception).lower())

    @patch("subprocess.run")
    def test_nonzero_returncode_raises_runtime_error(self, mock_run):
        """returncode != 0이면 RuntimeError, stderr 내용 포함."""
        mock_run.return_value = _make_proc(stdout="", stderr="auth error", returncode=1)

        client = ClaudeCodeCLIClient()
        with self.assertRaises(RuntimeError) as ctx:
            client.analyze("내용", "프롬프트")
        self.assertIn("auth error", str(ctx.exception))

    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=120))
    def test_timeout_raises_runtime_error(self, _mock_run):
        """subprocess 타임아웃 시 RuntimeError."""
        client = ClaudeCodeCLIClient()
        with self.assertRaises(RuntimeError) as ctx:
            client.analyze("내용", "프롬프트")
        self.assertIn("타임아웃", str(ctx.exception))

    @patch("subprocess.run")
    def test_invalid_json_raises_runtime_error(self, mock_run):
        """JSON 파싱 불가 stdout → RuntimeError."""
        mock_run.return_value = _make_proc(stdout="이것은 JSON이 아닙니다.")

        client = ClaudeCodeCLIClient()
        with self.assertRaises(RuntimeError) as ctx:
            client.analyze("내용", "프롬프트")
        self.assertIn("JSON 파싱 실패", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
