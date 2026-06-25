"""
GeminiClient 단위 테스트.

gemini CLI subprocess를 mock 처리해 외부 의존 없이 검증한다.

커버 범위:
  1. 정상 호출 → AnalysisResult 반환
  2. 이미지/pdf_image source_type → CLI에 file_path 인자 추가
  3. CLI 미설치(FileNotFoundError) → EnvironmentError
  4. returncode != 0 → RuntimeError (stderr 포함)
  5. TimeoutExpired → RuntimeError
  6. JSON 파싱 실패 → RuntimeError
  7. 마크다운 코드펜스로 감싸인 JSON도 정상 파싱
"""
import json
import subprocess
import sys
import os
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from llm.gemini_client import GeminiClient


def _make_proc(stdout: str = "", stderr: str = "", returncode: int = 0) -> MagicMock:
    """subprocess.run 반환값 mock 생성 헬퍼."""
    proc = MagicMock()
    proc.stdout = stdout
    proc.stderr = stderr
    proc.returncode = returncode
    return proc


_VALID_JSON = json.dumps({
    "summary": "테스트 요약입니다.\n두 번째 줄입니다.\n세 번째 줄입니다.",
    "errors": ["오류1", "오류2"],
})


class TestGeminiClientNormal(unittest.TestCase):
    """정상 동작 케이스."""

    @patch("subprocess.run")
    def test_returns_analysis_result(self, mock_run):
        """정상 JSON stdout → AnalysisResult 반환, model_used 형식 검증."""
        mock_run.return_value = _make_proc(stdout=_VALID_JSON)

        client = GeminiClient()
        result = client.analyze("문서 내용", "시스템 프롬프트")

        self.assertEqual(result.summary, "테스트 요약입니다.\n두 번째 줄입니다.\n세 번째 줄입니다.")
        self.assertEqual(result.detected_errors, ["오류1", "오류2"])
        self.assertTrue(result.model_used.startswith("gemini/"))

    @patch("subprocess.run")
    def test_stdin_contains_system_and_user_prompt(self, mock_run):
        """stdin에 system_prompt와 masked_text가 모두 포함되는지 검증."""
        mock_run.return_value = _make_proc(stdout=_VALID_JSON)

        client = GeminiClient()
        client.analyze("사용자 입력", "시스템 지시")

        call_kwargs = mock_run.call_args
        stdin_text = call_kwargs.kwargs.get("input") or call_kwargs.args[1] if len(call_kwargs.args) > 1 else call_kwargs.kwargs.get("input", "")
        # subprocess.run의 input 인자 확인
        actual_input = mock_run.call_args.kwargs.get("input", "")
        self.assertIn("시스템 지시", actual_input)
        self.assertIn("사용자 입력", actual_input)
        # JSON 강제 지시 포함 여부
        self.assertIn("JSON", actual_input)

    @patch("subprocess.run")
    def test_image_source_type_passes_file_path_as_arg(self, mock_run):
        """source_type=image이면 file_path를 CLI 인자로 전달해야 한다."""
        mock_run.return_value = _make_proc(stdout=_VALID_JSON)

        client = GeminiClient()
        client.analyze("내용", "프롬프트", source_type="image", file_path="/tmp/photo.png")

        cmd = mock_run.call_args.args[0]
        self.assertIn("/tmp/photo.png", cmd)

    @patch("subprocess.run")
    def test_pdf_image_source_type_passes_file_path_as_arg(self, mock_run):
        """source_type=pdf_image이면 file_path를 CLI 인자로 전달해야 한다."""
        mock_run.return_value = _make_proc(stdout=_VALID_JSON)

        client = GeminiClient()
        client.analyze("내용", "프롬프트", source_type="pdf_image", file_path="/tmp/scan.pdf")

        cmd = mock_run.call_args.args[0]
        self.assertIn("/tmp/scan.pdf", cmd)

    @patch("subprocess.run")
    def test_text_source_type_does_not_pass_file_path(self, mock_run):
        """source_type=xlsx 같은 텍스트 형식은 file_path를 CLI 인자에 포함하지 않는다."""
        mock_run.return_value = _make_proc(stdout=_VALID_JSON)

        client = GeminiClient()
        client.analyze("내용", "프롬프트", source_type="xlsx", file_path="/tmp/data.xlsx")

        cmd = mock_run.call_args.args[0]
        self.assertNotIn("/tmp/data.xlsx", cmd)

    @patch("subprocess.run")
    def test_fenced_json_parsed_correctly(self, mock_run):
        """마크다운 코드펜스(```json ... ```)로 감싸인 JSON도 정상 파싱한다."""
        fenced = f"```json\n{_VALID_JSON}\n```"
        mock_run.return_value = _make_proc(stdout=fenced)

        client = GeminiClient()
        result = client.analyze("내용", "프롬프트")

        self.assertEqual(result.detected_errors, ["오류1", "오류2"])

    @patch.dict(os.environ, {"GEMINI_MODEL": "gemini-1.5-pro"})
    @patch("subprocess.run")
    def test_model_used_reflects_env_var(self, mock_run):
        """GEMINI_MODEL 환경변수가 model_used에 반영된다."""
        mock_run.return_value = _make_proc(stdout=_VALID_JSON)

        client = GeminiClient()
        result = client.analyze("내용", "프롬프트")

        self.assertEqual(result.model_used, "gemini/gemini-1.5-pro")


class TestGeminiClientErrors(unittest.TestCase):
    """에러 케이스."""

    @patch("subprocess.run", side_effect=FileNotFoundError("No such file"))
    def test_cli_not_installed_raises_environment_error(self, _mock_run):
        """gemini CLI 미설치 시 EnvironmentError, 메시지에 설치 안내 포함."""
        client = GeminiClient()
        with self.assertRaises(EnvironmentError) as ctx:
            client.analyze("내용", "프롬프트")
        self.assertIn("gemini", str(ctx.exception).lower())

    @patch("subprocess.run")
    def test_nonzero_returncode_raises_runtime_error(self, mock_run):
        """returncode != 0이면 RuntimeError, stderr 내용 포함."""
        mock_run.return_value = _make_proc(
            stdout="", stderr="API key invalid", returncode=1
        )

        client = GeminiClient()
        with self.assertRaises(RuntimeError) as ctx:
            client.analyze("내용", "프롬프트")
        self.assertIn("API key invalid", str(ctx.exception))

    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="gemini", timeout=120))
    def test_timeout_raises_runtime_error(self, _mock_run):
        """subprocess 타임아웃 시 RuntimeError."""
        client = GeminiClient()
        with self.assertRaises(RuntimeError) as ctx:
            client.analyze("내용", "프롬프트")
        self.assertIn("타임아웃", str(ctx.exception))

    @patch("subprocess.run")
    def test_invalid_json_raises_runtime_error(self, mock_run):
        """JSON 파싱 불가 stdout → RuntimeError."""
        mock_run.return_value = _make_proc(stdout="이것은 JSON이 아닙니다.")

        client = GeminiClient()
        with self.assertRaises(RuntimeError) as ctx:
            client.analyze("내용", "프롬프트")
        self.assertIn("JSON 파싱 실패", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
