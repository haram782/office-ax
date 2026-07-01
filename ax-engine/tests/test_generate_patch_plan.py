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
                "snippet_data": {"corrections": [{"cell": "A2"}]},
            },
        )

        self.assertIn("sales.xlsx", prompt)
        self.assertIn("excel", prompt)
        self.assertIn("A2", prompt)
        self.assertIn("A2를 고쳐줘", prompt)

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
