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


class TestTextChatMasking(unittest.TestCase):
    """
    채팅 경로 PII 마스킹 테스트.

    closed-beta-launch-plan-v1-ko.md 결정 11:
      text_chat도 analyze_document와 동일하게 LLM 전송 전 mask_pii를 적용한다.
      사용자 질문과 session_history(문서 발췌 포함 가능) 모두 마스킹 대상이다.
    """

    def _call_task(self, task_self, **kwargs):
        from tasks.text_chat import _run_text_chat
        return _run_text_chat(task_self, **kwargs)

    def _analyze_prompt(self, mock_client):
        """client.analyze에 실제로 전달된 프롬프트 텍스트를 꺼낸다."""
        call = mock_client.analyze.call_args
        return call.args[0] if call.args else ""

    @patch("tasks.text_chat.get_llm_client")
    @patch("tasks.text_chat._send_callback")
    def test_content_pii_is_masked_before_llm(self, mock_callback, mock_get_client):
        """사용자 질문 속 주민번호·전화번호가 LLM 전송 전에 마스킹된다."""
        mock_client = MagicMock()
        mock_client.analyze.return_value = _make_result("응답")
        mock_get_client.return_value = mock_client
        task_self = MagicMock()

        self._call_task(
            task_self,
            content="담당자 주민번호 900101-1234567, 연락처 010-1234-5678 정리해줘",
            chat_message_id=1,
            session_history=[],
        )

        prompt = self._analyze_prompt(mock_client)
        self.assertNotIn("900101-1234567", prompt)
        self.assertNotIn("010-1234-5678", prompt)
        self.assertIn("[REDACTED_ID]", prompt)
        self.assertIn("[REDACTED_PHONE]", prompt)

    @patch("tasks.text_chat.get_llm_client")
    @patch("tasks.text_chat._send_callback")
    def test_history_pii_is_masked_before_llm(self, mock_callback, mock_get_client):
        """session_history에 남은 계좌번호·이메일도 마스킹된다 (문서 발췌 방어)."""
        mock_client = MagicMock()
        mock_client.analyze.return_value = _make_result("응답")
        mock_get_client.return_value = mock_client
        task_self = MagicMock()

        history = [
            {"role": "assistant", "content": "계좌 110-1234-567890, 메일 lee@corp.co.kr 확인됨"},
        ]
        self._call_task(task_self, content="위 내용 요약해줘", chat_message_id=2, session_history=history)

        prompt = self._analyze_prompt(mock_client)
        self.assertNotIn("110-1234-567890", prompt)
        self.assertNotIn("lee@corp.co.kr", prompt)

    @patch("tasks.text_chat.get_llm_client")
    @patch("tasks.text_chat._send_callback")
    def test_normal_text_is_not_altered(self, mock_callback, mock_get_client):
        """[회귀] PII가 없는 일반 질문은 원문 그대로 전달된다."""
        mock_client = MagicMock()
        mock_client.analyze.return_value = _make_result("응답")
        mock_get_client.return_value = mock_client
        task_self = MagicMock()

        self._call_task(task_self, content="합계 행 추가하는 방법 알려줘", chat_message_id=3, session_history=[])

        prompt = self._analyze_prompt(mock_client)
        self.assertIn("합계 행 추가하는 방법 알려줘", prompt)

    @patch("tasks.text_chat.get_llm_client")
    @patch("tasks.text_chat._send_callback")
    def test_patch_intent_refined_prompt_restores_real_pii_value(self, mock_callback, mock_get_client):
        """
        [버그 수정] 사용자가 채팅으로 직접 준 값(예: 문서에 적어달라고 요청한
        이메일)이 의도 판별 단계에서 마스킹된 뒤 그 자리표시자가 그대로
        PatchPlan 생성으로 넘어가면, PatchPlan LLM이 "실제 값이 아니다"라고
        판단해 해당 작업 자체를 누락시킨다(실제로 재현된 버그).

        closed-beta-launch-plan-v1-ko.md 결정 11: PatchPlan 생성 단계는
        원문 전송이 본질(expected_context 정합) — 의도 판별 LLM 호출 자체는
        마스킹된 텍스트로 하되, 그 결과인 refined_prompt는 PatchPlan으로
        넘어가기 전에 실제 값으로 복원되어야 한다.
        """
        mock_client = MagicMock()
        mock_client.analyze.return_value = _make_usage_result(
            "", parsed_data={
                "type": "patch_intent",
                "refined_prompt": "연락처(이메일) 필드를 [REDACTED_EMAIL]로 입력",
            },
        )
        mock_get_client.return_value = mock_client
        task_self = MagicMock()
        task_self.app.send_task = MagicMock()

        self._call_task(
            task_self,
            content="이메일 haram@gmail.com 으로 입력해줘",
            chat_message_id=4, session_history=[], upload_id=5,
        )

        call_args = mock_callback.call_args
        result = call_args.kwargs.get("result") or call_args.args[2]
        self.assertIn("haram@gmail.com", result["refined_prompt"])
        self.assertNotIn("[REDACTED_EMAIL]", result["refined_prompt"])




class TestTextChatRagContext(unittest.TestCase):
    """
    RAG 자산 프롬프트 주입 테스트 (점검 발견 A-2).

    rag_files(백엔드가 소유 검증 후 전달한 파일 목록)의 텍스트를
    LLM 프롬프트에 참고 자료로 주입한다. 임베딩 검색 없이 전문 주입 —
    베타 규모(자산 소수·소용량)에서 충분하며, 마스킹 이후 단계가 아니라
    마스킹 이전에 주입해 PII 정책을 그대로 적용받는다.
    """

    def _call_task(self, task_self, **kwargs):
        from tasks.text_chat import _run_text_chat
        return _run_text_chat(task_self, **kwargs)

    def _analyze_prompt(self, mock_client):
        call = mock_client.analyze.call_args
        return call.args[0] if call.args else ""

    @patch("tasks.text_chat.get_llm_client")
    @patch("tasks.text_chat._send_callback")
    def test_rag_file_text_is_injected_into_prompt(self, mock_callback, mock_get_client):
        """rag_files의 파일 내용과 그룹명이 프롬프트에 포함된다."""
        import tempfile

        mock_client = MagicMock()
        mock_client.analyze.return_value = _make_result("응답")
        mock_get_client.return_value = mock_client
        task_self = MagicMock()

        with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False) as f:
            f.write("항목,내용\n어투,정중한 보고체로 작성합니다")
            rag_path = f.name

        self._call_task(
            task_self,
            content="이 어투로 요약해줘",
            chat_message_id=1,
            session_history=[],
            rag_files=[{"kind": "tone", "group_name": "보고서_어투", "path": rag_path}],
        )

        prompt = self._analyze_prompt(mock_client)
        self.assertIn("보고서_어투", prompt)
        self.assertIn("정중한 보고체", prompt)
        self.assertIn("이 어투로 요약해줘", prompt)

    @patch("tasks.text_chat.get_llm_client")
    @patch("tasks.text_chat._send_callback")
    def test_missing_rag_file_is_skipped_without_failure(self, mock_callback, mock_get_client):
        """[실패 격리] 없는 파일 경로는 건너뛰고 채팅은 정상 진행된다."""
        mock_client = MagicMock()
        mock_client.analyze.return_value = _make_result("응답")
        mock_get_client.return_value = mock_client
        task_self = MagicMock()

        output = self._call_task(
            task_self,
            content="질문",
            chat_message_id=2,
            session_history=[],
            rag_files=[{"kind": "form", "group_name": "없는_자산", "path": "/no/such/file.csv"}],
        )

        self.assertEqual(output["source_type"], "chat")
        self.assertIn("질문", self._analyze_prompt(mock_client))

    @patch("tasks.text_chat.get_llm_client")
    @patch("tasks.text_chat._send_callback")
    def test_without_rag_files_prompt_unchanged(self, mock_callback, mock_get_client):
        """[회귀] rag_files 없으면 기존 프롬프트 형태를 유지한다."""
        mock_client = MagicMock()
        mock_client.analyze.return_value = _make_result("응답")
        mock_get_client.return_value = mock_client
        task_self = MagicMock()

        self._call_task(task_self, content="일반 질문", chat_message_id=3, session_history=[])
        prompt = self._analyze_prompt(mock_client)
        self.assertNotIn("참고 자산", prompt)
        self.assertIn("[사용자] 일반 질문", prompt)



if __name__ == "__main__":
    unittest.main()
