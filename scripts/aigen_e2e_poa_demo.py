"""
AIGEN 포트폴리오용 "위임장 시연 1건 end-to-end" 기록 스크립트.

브라우저 UI를 통한 업로드/다운로드 대신, 실제 프로덕션 코드 경로
(ax-engine generate_patch_plan_with_anchor_verification → backend/workers
hwp_worker.mjs)를 그대로 호출해 "자연어 요청 → PatchPlan 생성 → 적용"
흐름을 재현한다. 이 세션에는 브라우저/화면 제어 도구가 없어 실제 웹 UI
업로드-다운로드-재열기를 사람이 보는 것처럼 재생할 수 없다 — 그 사실을
숨기지 않고 산출물(AIGEN_E2E_POA_RECORD.md)에 그대로 남긴다.

실행: ax-engine/.venv에서 `python scripts/aigen_e2e_poa_demo.py`
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

DOC_PATH = REPO_ROOT / "scripts" / "eval_docs" / "위임장.hwp"
PROMPT = "위임하는 사람 이름에 '박하람'을 채워줘"


def main():
    from parsers.hwp_parser import parse_hwp
    import tasks.generate_patch_plan as gpp

    original_bytes = DOC_PATH.read_bytes()

    parsed = parse_hwp(str(DOC_PATH))
    document_text = parsed.get("text", "") if isinstance(parsed, dict) else str(parsed)

    file_context = {
        "file_path": str(DOC_PATH),
        "source_type": "hwp",
        "document_text": document_text,
    }

    plan = gpp.generate_hwp_patch_plan_with_anchor_verification(PROMPT, file_context)
    operations = plan.get("operations", [])

    # ── 적용: hwp_worker.mjs를 그대로 호출(프로덕션과 동일한 변경 형식) ──────────
    changes = [
        {
            "operation_id": op.get("operation_id"),
            "original": op.get("original") or op.get("anchor", {}).get("target_text", ""),
            "replacement": op.get("replacement") or op.get("patch", {}).get("text", ""),
        }
        for op in operations
        if op.get("operation") == "replace_text"
    ]
    payload = {"input_b64": base64.b64encode(original_bytes).decode(), "changes": changes}
    result = subprocess.run(
        ["node", str(REPO_ROOT / "backend" / "workers" / "hwp_worker.mjs")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    worker_out = json.loads(result.stdout) if result.returncode == 0 else {"error": result.stderr}

    record = {
        "prompt": PROMPT,
        "operations": operations,
        "changes_sent_to_worker": changes,
        "worker_stderr": result.stderr,
        "worker_result": {
            "applied": worker_out.get("applied"),
            "failed": worker_out.get("failed"),
        },
    }

    output_path = REPO_ROOT / "scripts" / "aigen_e2e_poa_demo_result.json"
    if "output_b64" in worker_out:
        applied_bytes = base64.b64decode(worker_out["output_b64"])
        applied_path = REPO_ROOT / "scripts" / "위임장_적용후.hwp"
        applied_path.write_bytes(applied_bytes)
        record["applied_file"] = str(applied_path)

    output_path.write_text(json.dumps(record, ensure_ascii=False, indent=2))
    print(json.dumps(record, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
