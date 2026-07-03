"""
text_chat Celery 태스크 단위 테스트.

커버 범위:
  1. LLM 응답 정상 → notify_chat_response 콜백 호출 확인
  2. LLM 실패 → retry 후 에러 콜백
  3. session_history가 analyze() 호출 시 컨텍스트에 포함되는지 확인
  4. 결과 dict에 source_type='chat' 포함 확인
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from llm.base import AnalysisResult


def _make_result(reply: str = "안녕하세요!") -> AnalysisResult:
    return AnalysisResult(
        summary=reply,
        detected_errors=[],
        model_used="mock-v1",
    )


def _make_usage_result(reply: str = "응답", parsed_data: dict | None = None) -> AnalysisResult:
    return AnalysisResult(
        summary=reply,
        detected_errors=[],
        model_used="gpt-4o",
        input_tokens=150,
        output_tokens=60,
        provider="openai",
        token_source="provider_reported",
        parsed_data=parsed_data or {},
    )


class TestTextChatTask(unittest.TestCase):
    """text_chat 태스크 동작 테스트."""

    def _call_task(self, task_self, **kwargs):
        """
        _run_text_chat 내부 함수를 직접 호출한다.
        bind=True Celery 태스크는 .run() 호출 시도 시 self 중복 바인딩 오류 발생.
        비즈니스 로직이 _run_text_chat에 분리되어 있으므로 이 함수를 직접 테스트한다.
        """
        from tasks.text_chat import _run_text_chat
        return _run_text_chat(task_self, **kwargs)

    @patch("tasks.text_chat.get_llm_client")
    @patch("tasks.text_chat._send_callback")
    def test_normal_response_calls_notify(self, mock_callback, mock_get_client):
        """LLM 정상 응답 → _send_callback에 reply가 담긴 result 전달."""
        mock_client = MagicMock()
        mock_client.analyze.return_value = _make_result("AI 응답입니다.")
        mock_get_client.return_value = mock_client

        task_self = MagicMock()
        task_self.app.send_task = MagicMock()

        self._call_task(
            task_self,
            content="안녕하세요",
            chat_message_id=42,
            session_history=[],
        )

        mock_callback.assert_called_once()
        call_args = mock_callback.call_args
        # _send_callback(task_self, chat_message_id, result) → args[2]
        result = call_args.kwargs.get("result") or call_args.args[2]
        self.assertEqual(result["summary"], "AI 응답입니다.")
        self.assertEqual(result["source_type"], "chat")
        self.assertEqual(result["errors"], [])

    @patch("tasks.text_chat.get_llm_client")
    @patch("tasks.text_chat._send_callback")
    def test_session_history_passed_to_analyze(self, mock_callback, mock_get_client):
        """session_history가 analyze() 호출에 컨텍스트로 전달된다."""
        mock_client = MagicMock()
        mock_client.analyze.return_value = _make_result("응답")
        mock_get_client.return_value = mock_client

        task_self = MagicMock()
        task_self.app.send_task = MagicMock()

        history = [
            {"role": "user", "content": "이전 질문"},
            {"role": "assistant", "content": "이전 답변"},
        ]
        self._call_task(task_self, content="새 질문", chat_message_id=1, session_history=history)

        analyze_call = mock_client.analyze.call_args
        prompt_text = analyze_call.args[0] if analyze_call.args else ""
        self.assertIn("이전 질문", prompt_text)
        self.assertIn("이전 답변", prompt_text)

    @patch("tasks.text_chat.get_llm_client")
    @patch("tasks.text_chat._send_callback")
    def test_result_has_chat_message_id(self, mock_callback, mock_get_client):
        """result dict에 chat_message_id가 포함된다."""
        mock_client = MagicMock()
        mock_client.analyze.return_value = _make_result("응답")
        mock_get_client.return_value = mock_client

        task_self = MagicMock()
        task_self.app.send_task = MagicMock()

        self._call_task(task_self, content="질문", chat_message_id=99, session_history=[])

        call_args = mock_callback.call_args
        # _send_callback(task_self, chat_message_id, result) → args[2]
        result = call_args.kwargs.get("result") or call_args.args[2]
        self.assertEqual(result.get("chat_message_id"), 99)

    @patch("tasks.text_chat.get_llm_client")
    @patch("tasks.text_chat._send_callback")
    def test_llm_failure_triggers_retry(self, mock_callback, mock_get_client):
        """LLM 실패 시 self.retry()가 호출된다."""
        mock_client = MagicMock()
        mock_client.analyze.side_effect = RuntimeError("LLM 연결 실패")
        mock_get_client.return_value = mock_client

        task_self = MagicMock()
        task_self.retry.side_effect = RuntimeError("최대 재시도 초과")
        task_self.app.send_task = MagicMock()

        with self.assertRaises(RuntimeError):
            self._call_task(task_self, content="질문", chat_message_id=7, session_history=[])

        task_self.retry.assert_called()

    @patch("tasks.text_chat.get_llm_client")
    @patch("tasks.text_chat._send_callback")
    def test_general_qa_result_contains_usage_keys(self, mock_callback, mock_get_client):
        """upload_id 없는 일반 Q&A 결과 dict에 usage/model/provider가 채워진다."""
        mock_client = MagicMock()
        mock_client.analyze.return_value = _make_usage_result("응답")
        mock_get_client.return_value = mock_client

        task_self = MagicMock()
        task_self.app.send_task = MagicMock()

        self._call_task(task_self, content="질문", chat_message_id=1, session_history=[])

        call_args = mock_callback.call_args
        result = call_args.kwargs.get("result") or call_args.args[2]
        self.assertEqual(result["usage"]["input_tokens"], 150)
        self.assertEqual(result["usage"]["output_tokens"], 60)
        self.assertEqual(result["usage"]["token_source"], "provider_reported")
        self.assertEqual(result["model"], "gpt-4o")
        self.assertEqual(result["provider"], "openai")

    @patch("tasks.text_chat.get_llm_client")
    @patch("tasks.text_chat._send_callback")
    def test_qa_with_upload_id_result_contains_usage_keys(self, mock_callback, mock_get_client):
        """upload_id 있는 qa 의도 판별 결과 dict에도 usage/model/provider가 채워진다."""
        mock_client = MagicMock()
        mock_client.analyze.return_value = _make_usage_result(
            "응답", parsed_data={"type": "qa", "reply": "답변입니다"},
        )
        mock_get_client.return_value = mock_client

        task_self = MagicMock()
        task_self.app.send_task = MagicMock()

        self._call_task(
            task_self, content="질문", chat_message_id=1, session_history=[], upload_id=5,
        )

        call_args = mock_callback.call_args
        result = call_args.kwargs.get("result") or call_args.args[2]
        self.assertEqual(result["usage"]["input_tokens"], 150)
        self.assertEqual(result["model"], "gpt-4o")
        self.assertEqual(result["provider"], "openai")

    @patch("tasks.text_chat.get_llm_client")
    @patch("tasks.text_chat._send_callback")
    def test_patch_intent_result_contains_usage_keys(self, mock_callback, mock_get_client):
        """patch_intent 의도 판별 결과 dict에도 usage/model/provider가 채워진다."""
        mock_client = MagicMock()
        mock_client.analyze.return_value = _make_usage_result(
            "", parsed_data={"type": "patch_intent", "refined_prompt": "A2 수정"},
        )
        mock_get_client.return_value = mock_client

        task_self = MagicMock()
        task_self.app.send_task = MagicMock()

        self._call_task(
            task_self, content="A2를 고쳐줘", chat_message_id=1, session_history=[], upload_id=5,
        )

        call_args = mock_callback.call_args
        result = call_args.kwargs.get("result") or call_args.args[2]
        self.assertEqual(result["usage"]["input_tokens"], 150)
        self.assertEqual(result["model"], "gpt-4o")
        self.assertEqual(result["provider"], "openai")


if __name__ == "__main__":
    unittest.main()
