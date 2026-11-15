"""
AIGEN 포트폴리오용 "처음 보는 서식으로 평가 1회" 스크립트.

기존 eval_patch_plan_baseline.py의 10개 케이스에 쓰지 않은 공공 서식 5개를
새로 평가한다. 기존 성공 판정(total_ops>0 and applied==total_ops)에
"기대값이 기대 칸(라벨 옆/같은 셀)에 실제로 들어갔는가"를 구조적으로
직접 확인하는 검사를 추가한다.

케이스별 기대값(어느 cellIdx에 무엇이 들어가야 하는가)은 LLM을 호출하기
전에, 문서의 실제 표 구조(getTableCellBboxes/getCellInfo)만 보고 먼저
고정했다 — 아래 CASES 딕�션의 "check" 필드가 그 고정값이다. 이 스크립트는
**딱 1번 실행**하고 결과를 있는 그대로 기록한다. 실패가 나와도 코드를
고쳐서 같은 세트로 다시 채점하지 않는다 — 고칠 지점이 보이면 별도 메모만
남긴다(아래 "발견된 개선 여지" 참고 — 이 파일은 실행 전에는 비워 두고
실행 후 결과를 보고서만 채운다).

실행: ax-engine/.venv에서 `python scripts/aigen_strict_eval_new_docs.py`
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

DOCS_DIR = REPO_ROOT / "scripts" / "eval_docs_new"

# ── 사전 고정된 기대값 (LLM 호출 전, 문서 구조만 보고 결정) ──────────────────
CASES = [
    {
        "doc": "저당권설정등록신청서.hwp",
        "source_url": "https://www.sejong.go.kr/bbs/R4161/view.do?nttId=B000000076266Oy2nG1d&mno=sub07_02&pageIndex=2",
        "prompt": "저당권자 성명에 '박하람'을 채워줘",
        "check": {
            "type": "same_cell_append",
            "note": "cellIdx=18 '성명(명칭)'은 colSpan=19인 넓은 단일 셀 — 라벨과 쓸 공간이 한 셀에 있다. 같은 셀 안에 라벨+값이 이어붙어야 한다.",
            "cellIdx": 18,
            "ctrlIdx": 2,
            "parentPara": 0,
            "must_contain": ["성명", "박하람"],
        },
    },
    {
        "doc": "폐기물처리업신청서.hwp",
        "source_url": "https://www.sejong.go.kr/bbs/R4182/view.do?nttId=B000000080182Kk7mX5r&mno=sub06_03&pageIndex=1",
        "prompt": "신청인 성명(대표자)에 '박하람'을 채워줘",
        "check": {
            "type": "same_cell_append",
            "note": "cellIdx=19 '③ 성명(대표자)'는 colSpan=11인 넓은 단일 셀 — 라벨과 쓸 공간이 한 셀에 있다.",
            "cellIdx": 19,
            "ctrlIdx": 2,
            "parentPara": 0,
            "must_contain": ["성명", "박하람"],
        },
    },
    {
        "doc": "건설기계등록원부신청서.hwp",
        "source_url": "https://www.sejong.go.kr/bbs/R4161/view.do?nttId=B000000076287Sn0hX0j&mno=sub07_02&pageIndex=2",
        "prompt": "신청인 성명에 '박하람'을 채워줘",
        "check": {
            "type": "same_cell_append",
            "note": "cellIdx=15 '성명'은 colSpan=18인 넓은 단일 셀 — 라벨과 쓸 공간이 한 셀에 있다.",
            "cellIdx": 15,
            "ctrlIdx": 2,
            "parentPara": 0,
            "must_contain": ["성명", "박하람"],
        },
    },
    {
        "doc": "마약류양도승인신청서.hwp",
        "source_url": "https://www.sejong.go.kr/bbs/R2000/view.do?nttId=77968&mno=sub02_04&pageIndex=3",
        "prompt": "담당자 성명에 '박하람'을 채워줘",
        "check": {
            "type": "adjacent_cell",
            "note": "cellIdx=53 '담당자 성명'(라벨) 바로 다음 cellIdx=54가 빈 칸 — 고전적인 라벨+인접 빈칸 구조.",
            "label_cell_idx": 53,
            "value_cell_idx": 54,
            "ctrlIdx": 2,
            "parentPara": 0,
            "expected_value": "박하람",
        },
    },
    {
        "doc": "종합검사유효기간연장신청서.hwp",
        "source_url": "https://www.sejong.go.kr/bbs/R4161/view.do?nttId=B000000077585Lo1tQ6m&mno=sub07_02&cmsNoStr=&kind=&pageIndex=1",
        "prompt": "소유자 성명에 '박하람'을 채워줘",
        "check": {
            "type": "adjacent_cell",
            "note": "cellIdx=6 '성 명(상호)'(라벨) 바로 다음 cellIdx=7이 빈 칸 — 고전적인 라벨+인접 빈칸 구조.",
            "label_cell_idx": 6,
            "value_cell_idx": 7,
            "ctrlIdx": 2,
            "parentPara": 0,
            "expected_value": "박하람",
        },
    },
]


def apply_via_worker(original_bytes: bytes, operations: list) -> dict:
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
    if result.returncode != 0:
        return {"error": result.stderr, "changes": changes}
    out = json.loads(result.stdout)
    out["changes"] = changes
    out["stderr"] = result.stderr
    return out


def run_structural_check(output_b64: str, check: dict) -> dict:
    """
    적용된 HWP 바이트를 실제로 열어 지정된 cellIdx의 텍스트를 직접 읽어
    기대값과 비교한다 — operation 개수가 아니라 실제 문서 내용으로 판정한다.
    """
    script = """
const fs = require('fs');
(async () => {
  const initRhwp = require(process.argv[2]).default;
  const { HwpDocument } = require(process.argv[2]);
  await initRhwp({ module_or_path: fs.readFileSync(process.argv[3]) });
  const bytes = Buffer.from(process.argv[4], 'base64');
  const doc = new HwpDocument(new Uint8Array(bytes));
  const check = JSON.parse(process.argv[5]);
  const out = {};
  if (check.type === 'same_cell_append') {
    out.cell_text = doc.getTextInCell(0, check.parentPara, check.ctrlIdx, check.cellIdx, 0, 0, 500) || '';
  } else {
    out.label_text = doc.getTextInCell(0, check.parentPara, check.ctrlIdx, check.label_cell_idx, 0, 0, 500) || '';
    out.value_text = doc.getTextInCell(0, check.parentPara, check.ctrlIdx, check.value_cell_idx, 0, 0, 500) || '';
  }
  console.log(JSON.stringify(out));
})();
"""
    rhwp_js = str(REPO_ROOT / "frontend" / "node_modules" / "@rhwp" / "core" / "rhwp.js")
    wasm_path = str(REPO_ROOT / "frontend" / "node_modules" / "@rhwp" / "core" / "rhwp_bg.wasm")
    result = subprocess.run(
        ["node", "-e", script, rhwp_js, rhwp_js, wasm_path, output_b64, json.dumps(check)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        return {"structural_check_error": result.stderr}
    return json.loads(result.stdout)


def grade(check: dict, structural: dict) -> tuple[bool, str]:
    if "structural_check_error" in structural:
        return False, f"구조 검사 자체가 실패: {structural['structural_check_error']}"
    if check["type"] == "same_cell_append":
        text = structural.get("cell_text", "")
        missing = [s for s in check["must_contain"] if s not in text]
        if missing:
            return False, f"같은 셀 텍스트에 기대 문자열 누락: {missing} (실제: {text!r})"
        return True, f"같은 셀에 라벨+값 정상 포함 (실제: {text!r})"
    else:
        label = structural.get("label_text", "")
        value = structural.get("value_text", "")
        if check["expected_value"].strip() not in value.strip():
            return False, f"값 칸(cellIdx={check['value_cell_idx']})에 기대값 없음 (실제: {value!r})"
        if check["expected_value"].strip() in label.strip():
            return False, f"라벨 칸(cellIdx={check['label_cell_idx']})이 오염됨 — 값이 라벨에 섞여 들어감 (실제: {label!r})"
        return True, f"라벨 보존 + 값 칸에 정확히 들어감 (라벨: {label!r}, 값: {value!r})"


def main():
    import tasks.generate_patch_plan as gpp

    results = []
    for case in CASES:
        doc_path = DOCS_DIR / case["doc"]
        original_bytes = doc_path.read_bytes()
        from parsers.hwp_parser import parse_hwp

        parsed = parse_hwp(str(doc_path))
        document_text = parsed.get("text", "") if isinstance(parsed, dict) else str(parsed)
        file_context = {
            "file_path": str(doc_path),
            "source_type": "hwp",
            "document_text": document_text,
        }

        plan = gpp.generate_hwp_patch_plan_with_anchor_verification(case["prompt"], file_context)
        operations = plan.get("operations", [])
        worker_result = apply_via_worker(original_bytes, operations)

        basic_ok = len(operations) > 0 and len(worker_result.get("applied", [])) == len(
            [o for o in operations if o.get("operation") == "replace_text"]
        )

        strict_ok = False
        reason = "basic 조건(operation 수/적용 수 불일치)에서 이미 실패"
        structural = None
        if basic_ok and "output_b64" in worker_result:
            structural = run_structural_check(worker_result["output_b64"], case["check"])
            strict_ok, reason = grade(case["check"], structural)
        elif basic_ok:
            reason = f"적용 자체가 실패: {worker_result.get('error', worker_result.get('failed'))}"

        results.append(
            {
                "doc": case["doc"],
                "source_url": case["source_url"],
                "prompt": case["prompt"],
                "expected_check": case["check"],
                "proposed_operations": operations,
                "worker_applied": worker_result.get("applied"),
                "worker_failed": worker_result.get("failed"),
                "structural_check": structural,
                "strict_success": strict_ok,
                "reason": reason,
            }
        )
        print(f"[{'성공' if strict_ok else '실패'}] {case['doc']} — {case['prompt']}")
        print(f"    {reason}")

    success_count = sum(1 for r in results if r["strict_success"])
    print(f"\n엄격 판정 성공률: {success_count}/{len(CASES)}")

    out_path = REPO_ROOT / "scripts" / "aigen_strict_eval_new_docs_result.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"상세 결과: {out_path}")


if __name__ == "__main__":
    main()
