/**
 * HWP anchor 검증 전용 Node.js worker — 문서를 수정하지 않고 "읽기 전용" 검사만 한다.
 *
 * generate_patch_plan.py가 LLM이 제안한 anchor(target_text)를 실제로 적용
 * 가능한지 미리 확인(또는 재시도 루프에서 재확인)하는 데 쓴다. hwp_worker.mjs의
 * 공백-둔감 검색 로직을 그대로 재사용해, "치환은 안 하고 매치 개수/위치만
 * 돌려준다"는 점만 다르다.
 *
 * "찾았다"만으로는 안전을 보장하지 못한다 — 표 셀 라벨이 "성  명"처럼 하나의
 * 셀에 여러 토큰이 들어있을 때, anchor가 그중 일부("성")만 가리키면
 * hwp_worker.mjs는 그 자리에 값을 바로 끼워넣어 라벨을 "성 박하람 명"처럼
 * 두 동강 낸다(찾기는 성공, 적용하면 문서 깨짐). 그래서 이 워커는
 * hwp_worker.mjs가 실제로 취할 경로(같은 셀 직접 치환 vs 옆 빈 칸에 값만 삽입)를
 * 미리 재현해, "찾았지만 적용하면 깨지는" 경우를 found=false로 보고한다.
 *
 * stdin  : JSON { input_b64, anchors: [{ operation_id, target_text, replacement }] }
 * stdout : JSON { results: [{ operation_id, found, match_count, used_query, reason? }] }
 * stderr : 로그 전용
 */
import initRhwp, { HwpDocument } from '../../frontend/node_modules/@rhwp/core/rhwp.js';
import { readFileSync } from 'node:fs';
import { searchAllTextWhitespaceTolerant } from './hwp_search_utils.mjs';
import { isSafeMatch } from './hwp_cell_utils.mjs';

async function readStdin() {
  const chunks = [];
  for await (const chunk of process.stdin) {
    chunks.push(chunk);
  }
  return Buffer.concat(chunks).toString('utf-8');
}

async function main() {
  let input;
  try {
    const raw = await readStdin();
    input = JSON.parse(raw);
  } catch (err) {
    process.stderr.write(`[hwp_verify_anchor] stdin 파싱 실패: ${err.message}\n`);
    process.exit(1);
  }

  const { input_b64, anchors } = input;
  const hwpBytes = new Uint8Array(Buffer.from(input_b64, 'base64'));

  const wasmPath = new URL(
    '../../frontend/node_modules/@rhwp/core/rhwp_bg.wasm',
    import.meta.url
  );
  try {
    const wasmBytes = readFileSync(wasmPath);
    await initRhwp({ module_or_path: wasmBytes });
  } catch (err) {
    process.stderr.write(`[hwp_verify_anchor] WASM 초기화 실패: ${err.message}\n`);
    process.exit(1);
  }

  let doc;
  try {
    doc = new HwpDocument(hwpBytes);
  } catch (err) {
    process.stderr.write(`[hwp_verify_anchor] HWP 로드 실패: ${err.message}\n`);
    process.exit(1);
  }

  const results = (anchors || []).map(({ operation_id, target_text, replacement }) => {
    const { matches, usedQuery } = searchAllTextWhitespaceTolerant(doc, target_text || '');
    if (matches.length === 0) {
      return { operation_id, found: false, match_count: 0, used_query: usedQuery, reason: 'not_found' };
    }

    // 본문 문단 매치(cellContext 없음)는 그 자리 치환이라 깨질 위험이 없다.
    // 표 셀 매치는 실제로 안전하게 적용 가능한 경우만 센다.
    const safeMatches = matches.filter((m) => isSafeMatch(doc, m, target_text, replacement));

    return {
      operation_id,
      found: safeMatches.length > 0,
      match_count: safeMatches.length,
      used_query: usedQuery,
      reason: safeMatches.length > 0 ? null : 'fragment_match_unsafe',
    };
  });

  process.stdout.write(JSON.stringify({ results }));
}

main().catch((err) => {
  process.stderr.write(`[hwp_verify_anchor] 예기치 않은 오류: ${err.message}\n${err.stack}\n`);
  process.exit(1);
});
