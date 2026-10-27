"""
PatchPlan 생성 → 실제 hwp_worker.mjs 적용 성공률 측정 스크립트.

Django/Celery/Docker 없이 ax-engine 함수(generate_patch_plan.
generate_hwp_patch_plan_with_anchor_verification)와 backend/workers/hwp_worker.mjs를
직접 연결해, 여러 (샘플 문서, 자연어 지시) 조합에 대해 "LLM이 만든 anchor가 실제로
안전하게 적용되는지"를 측정한다.

재실행 가능하게 만들어서, 추후 수정 전후 성공률을 비교하는 용도로도 쓴다.
각 케이스마다 재시도 과정(trace)도 함께 기록해 실패 원인을 바로 분석할 수 있다.

실행: ax-engine .venv 안에서
  python3 scripts/eval_patch_plan_baseline.py
"""
import base64
import json
import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("LLM_PROVIDER", "claude_cli")

REPO_ROOT = Path(__file__).resolve().parent.parent
AX_ENGINE_DIR = REPO_ROOT / "ax-engine"
sys.path.insert(0, str(AX_ENGINE_DIR))

from parsers.hwp_parser import parse_hwp  # noqa: E402
import tasks.generate_patch_plan as gpp  # noqa: E402

SAMPLE_DOCS_DIR = Path("/Users/haram/orca/office-ax/sample-docs/hwp")
EVAL_DOCS_DIR = Path(__file__).resolve().parent / "eval_docs"

# (문서 경로, 자연어 지시) — 전부 "빈 양식에 값 채우기" 시나리오.
# 문서는 두 출처에서 가져온다: 기존 sample-docs(4개, 이번 세션에서 처음 확인한 묶음)
# + 웹에서 수집한 실제 정부 공개 서식 4개(eval_docs/, 법령 별지 서식 — 공공누리 성격의
# 표준 양식이라 평가용으로 쓰기에 적합하다).
CASES = [
    (SAMPLE_DOCS_DIR / "차용증-양식.hwp", "채권자 성명에 '박하람', 채무자 성명에 '김철수'를 채워줘"),
    (SAMPLE_DOCS_DIR / "차용증-양식.hwp", "채권자 성명에 '박하람'을 채워줘"),
    (SAMPLE_DOCS_DIR / "거래명세서-양식.hwp", "공급자 상호를 '오르카 주식회사'로 채워줘"),
    (SAMPLE_DOCS_DIR / "공문서-양식-한글.hwp", "제목을 '회의 일정 안내'로 채워줘"),
    (SAMPLE_DOCS_DIR / "상가임대차표준계약서-양식.hwp", "보증금을 '오천만원'으로 채워줘"),
    (EVAL_DOCS_DIR / "위임장.hwp", "위임하는 사람 이름에 '박하람'을 채워줘"),
    (EVAL_DOCS_DIR / "위임장.hwp", "위임하는 사람 이름에 '박하람', 위임받는 사람 이름에 '김철수'를 채워줘"),
    (EVAL_DOCS_DIR / "등록번호판재발급신청서.hwp", "소유자 성명에 '박하람'을 채워줘"),
    (EVAL_DOCS_DIR / "진료기록열람동의서.hwp", "환자 본인 성명에 '박하람'을 채워줘"),
    (EVAL_DOCS_DIR / "자동차멸실인정서신청서.hwp", "소유자 성명에 '박하람'을 채워줘"),
]


def apply_via_worker(original_bytes: bytes, operations: list[dict]) -> dict:
    changes = [
        {
            "operation_id": op.get("operation_id", f"op_{i}"),
            "original": op.get("original", ""),
            "replacement": op.get("replacement", ""),
            "anchor": op.get("anchor", {}),
        }
        for i, op in enumerate(operations)
        if op.get("operation") == "replace_text"
    ]
    if not changes:
        return {"applied": [], "failed": [], "note": "no replace_text operations"}

    payload = {
        "input_b64": base64.b64encode(original_bytes).decode(),
        "changes": changes,
    }
    result = subprocess.run(
        ["node", "backend/workers/hwp_worker.mjs"],
        input=json.dumps(payload).encode(),
        capture_output=True,
        timeout=30,
        cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        return {"applied": [], "failed": [], "note": f"worker returncode={result.returncode}: {result.stderr.decode(errors='replace')[:200]}"}
    return json.loads(result.stdout.decode())


class _TraceRecorder:
    """
    _call_llm_patch_plan / _verify_hwp_anchors 호출을 가로채 재시도 과정을 기록한다.

    매 케이스마다 "진짜 원본 함수"를 기준으로 다시 감싸고, 끝나면 반드시
    원복한다 — 그렇지 않으면 이전 케이스의 wrapper가 "orig"로 캡처된 채
    남아있어서, 다음 케이스 호출이 이전 wrapper를 통해 체이닝되며 서로
    다른 케이스의 기록이 섞인다(실제로 이 버그로 1회차 결과에 10개 케이스
    전체의 시도가 누적되어 나타난 적이 있다 — with문으로 범위를 명확히
    분리해 재발을 방지한다).
    """

    def __init__(self):
        self.attempts: list[dict] = []

    def __enter__(self):
        self._orig_call_llm = gpp._call_llm_patch_plan
        self._orig_verify = gpp._verify_hwp_anchors

        def traced_call_llm(prompt, file_context):
            plan = self._orig_call_llm(prompt, file_context)
            self.attempts.append({
                "type": "llm_call",
                "prompt_tail": prompt[-200:],
                "operations": [
                    {"original": op.get("original"), "replacement": op.get("replacement")}
                    for op in plan.get("operations", [])
                ],
            })
            return plan

        def traced_verify(original_bytes, operations):
            result = self._orig_verify(original_bytes, operations)
            self.attempts.append({"type": "verify", "result": result})
            return result

        gpp._call_llm_patch_plan = traced_call_llm
        gpp._run_generate_patch_plan.__globals__["_call_llm_patch_plan"] = traced_call_llm
        gpp._verify_hwp_anchors = traced_verify
        gpp.generate_hwp_patch_plan_with_anchor_verification.__globals__["_verify_hwp_anchors"] = traced_verify
        return self

    def __exit__(self, *exc_info):
        gpp._call_llm_patch_plan = self._orig_call_llm
        gpp._run_generate_patch_plan.__globals__["_call_llm_patch_plan"] = self._orig_call_llm
        gpp._verify_hwp_anchors = self._orig_verify
        gpp.generate_hwp_patch_plan_with_anchor_verification.__globals__["_verify_hwp_anchors"] = self._orig_verify


def run_case(path: Path, prompt: str) -> dict:
    original_bytes = path.read_bytes()
    text, _ = parse_hwp(path)

    with _TraceRecorder() as recorder:
        plan = gpp.generate_hwp_patch_plan_with_anchor_verification(prompt, {
            "filename": path.name,
            "source_type": "hwp",
            "document_text": text,
            "file_path": str(path),
            "snippet_data": {},
        })
    operations = plan.get("operations", [])
    worker_result = apply_via_worker(original_bytes, operations)

    total_ops = len([o for o in operations if o.get("operation") == "replace_text"])
    applied = len(worker_result.get("applied", []))
    return {
        "filename": path.name,
        "prompt": prompt,
        "proposed_ops": total_ops,
        "applied_ops": applied,
        "success": total_ops > 0 and applied == total_ops,
        "operations": operations,
        "worker_result": worker_result,
        "trace": recorder.attempts,
    }


def main():
    results = [run_case(p, prompt) for p, prompt in CASES]

    print("\n" + "=" * 70)
    print("결과")
    print("=" * 70)
    for r in results:
        status = "성공" if r["success"] else "실패"
        print(f"[{status}] {r['filename']} — {r['prompt']!r}")
        print(f"    제안 operation 수: {r['proposed_ops']}, 적용된 수: {r['applied_ops']}")
        if not r["success"]:
            for f in r["worker_result"].get("failed", []):
                print(f"    - 실패: {f}")
            if r["worker_result"].get("note"):
                print(f"    - note: {r['worker_result']['note']}")
            llm_attempts = [a for a in r["trace"] if a["type"] == "llm_call"]
            print(f"    - LLM 시도 횟수: {len(llm_attempts)}")
            for i, a in enumerate(llm_attempts):
                for op in a["operations"]:
                    print(f"      시도{i+1}: {op['original']!r} -> {op['replacement']!r}")

    n = len(results)
    n_success = sum(1 for r in results if r["success"])
    print()
    print(f"성공률: {n_success}/{n} ({n_success/n*100:.0f}%)")

    out_path = Path(__file__).parent / "eval_patch_plan_baseline_result.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"상세 결과(재시도 trace 포함) 저장: {out_path}")


if __name__ == "__main__":
    main()
