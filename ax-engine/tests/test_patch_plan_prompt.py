"""
PATCH_PLAN_SYSTEM_PROMPT 회귀 테스트.

실행: cd ax-engine && .venv/bin/python tests/test_patch_plan_prompt.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from prompts.patch_plan import PATCH_PLAN_SYSTEM_PROMPT


class PatchPlanPromptAllowedOperationsTest(unittest.TestCase):
    """
    [버그 수정] redact_overlay는 backend/apps/documents/patcher.py에 완전히
    구현·테스트돼 있고(_apply_pdf_redact_overlay, 한글 폰트 임베드 포함),
    docs/patch_plan_schema.md·stack-library-audit-v1-ko.md에도 PDF에 값을
    "써넣는" 용도로 명시돼 있는데, 이 시스템 프롬프트가 실수로 허용
    목록에서 빠진 채 "NOT redact_overlay"로 명시 제외돼 있었다.

    실사용 재현: PDF 빈 칸에 값을 채워달라는 요청에서 LLM이 유일하게
    남은 선택지인 annotate를 골랐는데, annotate는 하이라이트 주석만
    추가하고 실제 페이지 내용은 바꾸지 않아(patcher.py 주석: "annotate는
    텍스트를 바꾸지 않으므로") 화면에 아무 값도 안 보였다.
    """

    def test_redact_overlay_is_allowed_not_excluded(self):
        self.assertIn(
            "redact_overlay", PATCH_PLAN_SYSTEM_PROMPT,
            "redact_overlay가 프롬프트에서 언급조차 안 됨",
        )
        self.assertNotIn(
            "NOT redact_overlay", PATCH_PLAN_SYSTEM_PROMPT,
            "redact_overlay가 명시적으로 제외돼 있음 — PDF 빈 칸 채우기에 쓸 유일한 수단인데 못 쓰게 막고 있다",
        )

    def test_annotate_guidance_clarifies_it_does_not_change_visible_text(self):
        """annotate를 값 채우기 용도로 오용하지 않도록 명확한 안내가 있어야 한다."""
        self.assertIn("annotate", PATCH_PLAN_SYSTEM_PROMPT)
        # "annotate" 관련 설명 어딘가에 "하이라이트"/"highlight" 언급이 있어야
        # "값을 채우는" 용도가 아님을 LLM이 알 수 있다.
        annotate_idx = PATCH_PLAN_SYSTEM_PROMPT.index("annotate (PDF)") \
            if "annotate (PDF)" in PATCH_PLAN_SYSTEM_PROMPT else -1
        self.assertNotEqual(annotate_idx, -1, "annotate 전용 사용법 안내가 없음")


if __name__ == "__main__":
    unittest.main()
