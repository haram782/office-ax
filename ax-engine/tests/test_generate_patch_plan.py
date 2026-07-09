"""
PatchPlan 생성 태스크 단위 테스트.

LLM_PROVIDER에 따른 실제 클라이언트 선택은 get_llm_client()가 담당하므로
여기서는 외부 CLI/API를 호출하지 않고 mock 클라이언트로 동작 계약만 검증한다.
"""
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from llm.base import AnalysisResult
from tasks.generate_patch_plan import (
    _build_patch_plan_prompt,
    _coerce_patch_plan,
    _document_text_for_simple_plan,
    _maybe_build_simple_replace_plan,
    _run_generate_patch_plan,
    _send_callback,
)


_PLAN = {
    "schema": "office_ax.patch_plan.v0",
    "plan_id": "plan_ax_test_001",
    "summary": "테스트 수정 계획",
    "operations": [
        {
            "operation_id": "op_001",
            "format": "excel",
            "operation": "replace_cell",
            "title": "A2 교체",
            "original": "20260101",
            "replacement": "2026-01-01",
            "reason": "날짜 형식 통일",
            "confidence": 0.9,
            "anchor": {"type": "cell", "sheet": "Sheet1", "cell": "A2"},
            "patch": {"method": "openpyxl_set_value", "value": "2026-01-01"},
            "risk": {"level": "low"},
        }
    ],
}


class GeneratePatchPlanTaskTest(unittest.TestCase):
    """PatchPlan 태스크 내부 함수 동작 테스트."""

    def test_build_prompt_contains_file_context_and_request(self):
        """LLM 입력에 파일명, 형식, 컨텍스트, 수정 요청이 포함된다."""
        prompt = _build_patch_plan_prompt(
            "A2를 고쳐줘",
            {
                "filename": "sales.xlsx",
                "source_type": "excel",
                "document_text": "문서 본문 test",
                "snippet_data": {"corrections": [{"cell": "A2"}]},
            },
        )

        self.assertIn("sales.xlsx", prompt)
        self.assertIn("excel", prompt)
        self.assertIn("문서 본문 test", prompt)
        self.assertIn("A2", prompt)
        self.assertIn("A2를 고쳐줘", prompt)

    def test_simple_hwp_replace_plan_uses_document_text_without_llm(self):
        """본문에 있는 명시적 텍스트 교체는 deterministic replace_text PatchPlan으로 만든다."""
        plan = _maybe_build_simple_replace_plan(
            "문서 내 'test' 문구를 '박하람'으로 교체",
            {"source_type": "hwp", "document_text": "이것은 테스트 문서입니다 Test"},
        )

        self.assertIsNotNone(plan)
        op = plan["operations"][0]
        self.assertEqual(op["format"], "hwp")
        self.assertEqual(op["operation"], "replace_text")
        self.assertEqual(op["original"], "test")
        self.assertEqual(op["replacement"], "박하람")
        self.assertEqual(op["anchor"]["occurrence"], 1)

    def test_simple_replace_plan_returns_none_when_text_absent(self):
        """본문에 없는 텍스트는 deterministic plan을 만들지 않고 LLM 경로로 넘긴다."""
        plan = _maybe_build_simple_replace_plan(
            "문서 내 'missing' 문구를 '박하람'으로 교체",
            {"source_type": "hwp", "document_text": "이것은 테스트 문서입니다 Test"},
        )

        self.assertIsNone(plan)

    @patch("tasks.generate_patch_plan.parse_hwp", return_value=("이것은 테스트 문서입니다 Test", {"method": "rhwp"}))
    def test_simple_hwp_replace_plan_reads_file_when_document_text_missing(self, mock_parse_hwp):
        """기존 분석 레코드처럼 document_text가 없어도 HWP 원본 파일 fallback을 사용한다."""
        plan = _maybe_build_simple_replace_plan(
            "문서 내 'test' 문구를 '박하람'으로 교체",
            {"source_type": "hwp", "file_path": "/tmp/sample.hwp"},
        )

        self.assertIsNotNone(plan)
        self.assertEqual(plan["operations"][0]["operation"], "replace_text")
        mock_parse_hwp.assert_called_once()

    @patch("tasks.generate_patch_plan.parse_hwp", return_value=("본문 Test", {"method": "rhwp"}))
    def test_document_text_for_simple_plan_uses_hwp_file_fallback(self, _mock_parse_hwp):
        text = _document_text_for_simple_plan({"source_type": "hwp", "file_path": "/tmp/sample.hwp"})

        self.assertEqual(text, "본문 Test")

    @patch("tasks.generate_patch_plan.get_llm_client")
    def test_run_generate_patch_plan_uses_registered_llm_client(self, mock_get_client):
        """get_llm_client()로 선택된 클라이언트가 PatchPlan 생성을 수행한다."""
        mock_client = MagicMock()
        mock_client.analyze.return_value = AnalysisResult(
            summary="",
            model_used="gemini/mock",
            parsed_data=dict(_PLAN),
        )
        mock_get_client.return_value = mock_client

        plan = _run_generate_patch_plan(
            "날짜 수정",
            {"filename": "sales.xlsx", "source_type": "excel", "snippet_data": {}},
        )

        self.assertEqual(plan["plan_id"], "plan_ax_test_001")
        self.assertEqual(plan["model_used"], "gemini/mock")
        mock_get_client.assert_called_once()
        mock_client.analyze.assert_called_once()

    @patch("tasks.generate_patch_plan.get_llm_client")
    def test_run_generate_patch_plan_skips_llm_for_simple_hwp_replace(self, mock_get_client):
        """단순 HWP 텍스트 교체는 LLM 호출 없이 PatchPlan을 생성한다."""
        plan = _run_generate_patch_plan(
            "문서 내 'test' 문구를 '박하람'으로 교체",
            {"filename": "sample.hwp", "source_type": "hwp", "document_text": "Test"},
        )

        self.assertEqual(plan["operations"][0]["operation"], "replace_text")
        mock_get_client.assert_not_called()

    @patch("tasks.generate_patch_plan.get_llm_client")
    @patch("tasks.generate_patch_plan.parse_hwp", return_value=("Test", {"method": "rhwp"}))
    def test_run_generate_patch_plan_skips_llm_with_hwp_file_fallback(self, _mock_parse_hwp, mock_get_client):
        """document_text 없는 기존 업로드도 file_path fallback으로 LLM을 건너뛴다."""
        plan = _run_generate_patch_plan(
            "문서 내 'test' 문구를 '박하람'으로 교체",
            {"filename": "sample.hwp", "source_type": "hwp", "file_path": "/tmp/sample.hwp"},
        )

        self.assertEqual(plan["operations"][0]["replacement"], "박하람")
        mock_get_client.assert_not_called()

    def test_coerce_patch_plan_contains_usage_keys(self):
        """PatchPlan 결과 dict에 usage/model/provider 계약 키가 채워진다."""
        result = AnalysisResult(
            summary="",
            model_used="gemini/gemini-2.0-flash",
            input_tokens=90,
            output_tokens=40,
            provider="gemini",
            token_source="estimated",
            parsed_data=dict(_PLAN),
        )

        plan = _coerce_patch_plan(result)

        self.assertEqual(plan["usage"]["input_tokens"], 90)
        self.assertEqual(plan["usage"]["output_tokens"], 40)
        self.assertEqual(plan["usage"]["token_source"], "estimated")
        self.assertEqual(plan["model"], "gemini/gemini-2.0-flash")
        self.assertEqual(plan["provider"], "gemini")

    def test_coerce_patch_plan_parses_summary_json_fallback(self):
        """parsed_data가 없을 때 summary JSON 문자열을 PatchPlan으로 파싱한다."""
        result = AnalysisResult(
            summary=json.dumps(_PLAN, ensure_ascii=False),
            model_used="mock",
            parsed_data={},
        )

        plan = _coerce_patch_plan(result)

        self.assertEqual(plan["plan_id"], "plan_ax_test_001")
        self.assertEqual(plan["operations"][0]["operation_id"], "op_001")

    def test_coerce_patch_plan_rejects_missing_operations(self):
        """operations가 없는 LLM 응답은 실패해야 한다."""
        result = AnalysisResult(
            summary=json.dumps({"plan_id": "bad_plan"}),
            model_used="mock",
            parsed_data={},
        )

        with self.assertRaises(ValueError):
            _coerce_patch_plan(result)

    def test_send_callback_uses_celery_queue(self):
        """콜백 결과는 Django celery 큐로 전달된다."""
        task_self = MagicMock()
        task_self.app.send_task = MagicMock()

        _send_callback(
            task_self,
            "chat.notify_patch_plan_generated",
            {"chat_message_id": 10, "upload_id": 20},
            _PLAN,
        )

        task_self.app.send_task.assert_called_once()
        self.assertEqual(
            task_self.app.send_task.call_args.args[0],
            "chat.notify_patch_plan_generated",
        )
        self.assertEqual(task_self.app.send_task.call_args.kwargs["queue"], "celery")
        self.assertEqual(
            task_self.app.send_task.call_args.kwargs["kwargs"]["result"]["plan_id"],
            "plan_ax_test_001",
        )


if __name__ == "__main__":
    unittest.main()
