/**
 * hwp_worker.mjs 검증용 probe 스크립트 (프로덕션 코드 아님).
 *
 * occurrence 기반 replaceText 정밀 치환이 의도대로 동작하는지
 * 실제 HWP 바이트 + subprocess 호출로 직접 검증한다.
 *
 * 실행: node test_hwp_worker.mjs
 */
import initRhwp, { HwpDocument } from '../../frontend/node_modules/@rhwp/core/rhwp.js';
import { readFileSync, writeFileSync, unlinkSync } from 'node:fs';
import { spawnSync } from 'node:child_process';

const wasmPath = new URL('../../frontend/node_modules/@rhwp/core/rhwp_bg.wasm', import.meta.url);
const wasmBytes = readFileSync(wasmPath);
await initRhwp({ module_or_path: wasmBytes });

// ── "사원"이 3번 등장하는 테스트용 HWP 생성 ────────────────────────────────────
function buildMultiOccurrenceHwp() {
  const baseBytes = new Uint8Array(readFileSync(new URL('../apps/documents/fixtures/sample.hwp', import.meta.url)));
  const doc = new HwpDocument(baseBytes);
  doc.insertText(0, 0, doc.getParagraphLength(0, 0), ' 사원 사원 사원');
  return Buffer.from(doc.exportHwp());
}

function countMatches(hwpBuffer, text) {
  const doc = new HwpDocument(new Uint8Array(hwpBuffer));
  const matches = JSON.parse(doc.searchAllText(text, false, true));
  return matches.length;
}

function runWorker(inputBytes, changes) {
  const payload = JSON.stringify({
    input_b64: inputBytes.toString('base64'),
    changes,
  });
  const result = spawnSync('node', [new URL('./hwp_worker.mjs', import.meta.url).pathname], {
    input: payload,
    maxBuffer: 1024 * 1024 * 50,
  });
  if (result.status !== 0) {
    throw new Error(`worker 비정상 종료: ${result.stderr.toString()}`);
  }
  return JSON.parse(result.stdout.toString());
}

let passed = 0;
let failedCount = 0;

function assert(condition, message) {
  if (condition) {
    console.log(`  PASS: ${message}`);
    passed += 1;
  } else {
    console.log(`  FAIL: ${message}`);
    failedCount += 1;
  }
}

// ── 케이스 1: occurrence=1 → 1건만 교체, 나머지 2건 유지 ───────────────────────
console.log('\n[케이스 1] occurrence=1 → 첫 번째 매치만 교체');
{
  const input = buildMultiOccurrenceHwp();
  const before = countMatches(input, '사원');
  console.log(`  치환 전 "사원" 매치 수: ${before}`);

  const out = runWorker(input, [
    { operation_id: 'op1', original: '사원', replacement: 'XX', anchor: { occurrence: 1 } },
  ]);

  assert(out.applied.includes('op1'), 'op1이 applied에 포함됨');
  assert(out.failed.length === 0, 'failed가 비어있음');

  const outputBytes = Buffer.from(out.output_b64, 'base64');
  const afterOriginal = countMatches(outputBytes, '사원');
  const afterReplaced = countMatches(outputBytes, 'XX');
  console.log(`  치환 후 "사원" 매치 수: ${afterOriginal}, "XX" 매치 수: ${afterReplaced}`);
  assert(afterOriginal === before - 1, '치환 후 "사원" 매치가 1건 감소함 (전체치환 아님)');
  assert(afterReplaced === 1, '"XX"가 정확히 1건만 생김');
}

// ── 케이스 2: occurrence=2 → 두 번째 매치만 교체 ───────────────────────────────
console.log('\n[케이스 2] occurrence=2 → 두 번째 매치만 교체');
{
  const input = buildMultiOccurrenceHwp();
  const beforeDoc = new HwpDocument(new Uint8Array(input));
  const beforeMatches = JSON.parse(beforeDoc.searchAllText('사원', false, true));
  const secondMatchOffset = beforeMatches[1].charOffset;

  const out = runWorker(input, [
    { operation_id: 'op2', original: '사원', replacement: 'YY', anchor: { occurrence: 2 } },
  ]);

  assert(out.applied.includes('op2'), 'op2가 applied에 포함됨');

  const outputBytes = Buffer.from(out.output_b64, 'base64');
  const afterDoc = new HwpDocument(new Uint8Array(outputBytes));
  const len = afterDoc.getParagraphLength(0, 0);
  const fullText = afterDoc.getTextRange(0, 0, 0, len);
  console.log(`  치환 후 전체 텍스트: "${fullText}"`);
  assert(fullText.includes('YY'), '치환 후 텍스트에 YY가 포함됨');
  assert((fullText.match(/사원/g) || []).length === 2, '"사원"이 2건 그대로 유지됨 (1·3번째)');
}

// ── 케이스 3: 텍스트 없음 → failed, applied 비어있음 ───────────────────────────
console.log('\n[케이스 3] 존재하지 않는 텍스트 → failed');
{
  const input = buildMultiOccurrenceHwp();
  const out = runWorker(input, [
    { operation_id: 'op3', original: '존재하지않는텍스트XYZ', replacement: 'ZZ', anchor: { occurrence: 1 } },
  ]);

  assert(out.applied.length === 0, 'applied가 비어있음');
  assert(out.failed.length === 1 && out.failed[0].operation_id === 'op3', 'op3이 failed에 기록됨');
  console.log(`  failed 사유: ${out.failed[0].reason}`);
}

// ── 케이스 4: occurrence가 매치 수 초과 → failed ───────────────────────────────
console.log('\n[케이스 4] occurrence=10 (매치는 3건뿐) → failed');
{
  const input = buildMultiOccurrenceHwp();
  const out = runWorker(input, [
    { operation_id: 'op4', original: '사원', replacement: 'WW', anchor: { occurrence: 10 } },
  ]);

  assert(out.applied.length === 0, 'applied가 비어있음');
  assert(out.failed.length === 1 && out.failed[0].operation_id === 'op4', 'op4이 failed에 기록됨');
  console.log(`  failed 사유: ${out.failed[0].reason}`);
}

// ── 케이스 5: anchor 없음(기존 호환) → occurrence 기본값 1로 첫 매치 교체 ───────
console.log('\n[케이스 5] anchor.occurrence 없음 → 기본값 1로 첫 매치만 교체');
{
  const input = buildMultiOccurrenceHwp();
  const before = countMatches(input, '사원');

  const out = runWorker(input, [
    { operation_id: 'op5', original: '사원', replacement: 'NOANCHOR' }, // anchor 필드 자체가 없음
  ]);

  assert(out.applied.includes('op5'), 'op5가 applied에 포함됨 (anchor 없어도 기본값 1로 동작)');
  const outputBytes = Buffer.from(out.output_b64, 'base64');
  const afterOriginal = countMatches(outputBytes, '사원');
  assert(afterOriginal === before - 1, 'anchor 없을 때도 1건만 교체됨 (전체치환 아님)');
}

// ── 케이스 6: 원본 공백 2칸 vs 검색어 공백 1칸 → 공백-둔감 매칭으로 성공 ─────────
// hwp_text_extract.mjs의 normalizeText()가 연속 공백을 1칸으로 뭉개서 LLM에게
// 보여주므로, PatchPlan의 original은 "주 소"(1칸)처럼 뭉개진 형태로 생성된다.
// 실제 문서에는 "주  소"(2칸)로 저장돼 있어 정확 일치 검색이 실패하던 버그.
console.log('\n[케이스 6] 원본 공백 2칸, 검색어 공백 1칸 → 공백-둔감 매칭으로 성공해야 함');
{
  const baseBytes = new Uint8Array(readFileSync(new URL('../apps/documents/fixtures/sample.hwp', import.meta.url)));
  const doc = new HwpDocument(baseBytes);
  doc.insertText(0, 0, doc.getParagraphLength(0, 0), '주  소 테스트');
  const input = Buffer.from(doc.exportHwp());

  const before = countMatches(input, '주  소');
  console.log(`  원본 "주  소"(공백 2칸) 매치 수: ${before}`);
  assert(before > 0, '원본에는 공백 2칸 텍스트가 실제로 존재함 (테스트 전제 확인)');

  const out = runWorker(input, [
    { operation_id: 'op6', original: '주 소', replacement: '주소 분당동 102-1', anchor: { occurrence: 1 } },
  ]);

  assert(out.applied.includes('op6'), 'op6이 applied에 포함됨 (공백 개수가 달라도 매칭 성공)');
  if (out.failed.length > 0) {
    console.log(`  failed 사유: ${JSON.stringify(out.failed)}`);
  }

  const outputBytes = Buffer.from(out.output_b64, 'base64');
  const len = new HwpDocument(new Uint8Array(outputBytes)).getParagraphLength(0, 0);
  const fullText = new HwpDocument(new Uint8Array(outputBytes)).getTextRange(0, 0, 0, len);
  console.log(`  치환 후 전체 텍스트: "${fullText}"`);
  assert(fullText.includes('분당동 102-1'), '치환 결과가 실제 반영됨');
}

// ── 케이스 7: 표 셀 내부 매치 → 셀 안에서 치환 (본문 문단에 삽입되면 안 됨) ─────
// 실제 공문서 양식: "주  소" 라벨이 표 셀 안에만 존재하고, 표를 담는 본문 문단은
// 빈 문단이다. cellContext를 무시하고 본문 좌표로 replaceText하면 라벨 셀은
// 그대로 남고 빈 본문 문단에 새 줄로 텍스트가 삽입되는 버그가 있었다.
console.log('\n[케이스 7] 표 셀 내부 매치 → 셀 안에서 치환되고 본문에 새 줄이 생기지 않아야 함');
{
  const input = readFileSync(new URL('../../sample-docs/공문서-양식-한글.hwp', import.meta.url));

  const out = runWorker(input, [
    { operation_id: 'op7', original: '주 소', replacement: '주 소 분당동 102-1', anchor: { occurrence: 1 } },
  ]);

  assert(out.applied.includes('op7'), 'op7이 applied에 포함됨');

  const outputBytes = Buffer.from(out.output_b64, 'base64');
  const afterDoc = new HwpDocument(new Uint8Array(outputBytes));

  const bodyMatches = JSON.parse(afterDoc.searchAllText('분당동 102-1', false, false));
  assert(bodyMatches.length === 0, '치환 결과가 본문 문단에 새로 삽입되지 않음 (본문 검색 0건)');

  const cellMatches = JSON.parse(afterDoc.searchAllText('분당동 102-1', false, true));
  assert(cellMatches.length === 1, '치환 결과가 문서에 정확히 1건 존재함');
  assert(cellMatches[0]?.cellContext != null, '치환 결과가 표 셀 내부에 있음 (cellContext 존재)');
}

// ── 케이스 8: 라벨 셀 + 빈 값 셀 구조 → 값은 옆의 빈 셀에, 라벨은 그대로 ────────
// 공문서 표는 [주  소][빈 값 셀][TEL]... 라벨/값 셀 쌍 구조다. replacement가
// "라벨 + 값" 형태일 때 라벨 셀 안에 통째로 넣으면 좁은 라벨 셀에서 여러 줄로
// 감겨 정렬이 깨진다 — 라벨 셀은 그대로 두고 값만 옆의 빈 셀에 넣어야 한다.
console.log('\n[케이스 8] 라벨 셀 옆에 빈 값 셀이 있으면 값만 그 셀에 넣고 라벨은 유지해야 함');
{
  const input = readFileSync(new URL('../../sample-docs/공문서-양식-한글.hwp', import.meta.url));

  const out = runWorker(input, [
    { operation_id: 'op8', original: '주 소', replacement: '주 소 분당동 102-1', anchor: { occurrence: 1 } },
  ]);

  assert(out.applied.includes('op8'), 'op8이 applied에 포함됨');

  const outputBytes = Buffer.from(out.output_b64, 'base64');
  const afterDoc = new HwpDocument(new Uint8Array(outputBytes));

  const labelCellText = afterDoc.getTextInCell(0, 2, 0, 0, 0, 0, 100);
  assert(labelCellText === '주  소', `라벨 셀(cell 0)은 원본 그대로 유지됨 (실제: ${JSON.stringify(labelCellText)})`);

  const valueCellText = afterDoc.getTextInCell(0, 2, 0, 1, 0, 0, 100);
  assert(valueCellText === '분당동 102-1', `값이 옆의 빈 값 셀(cell 1)에 들어감 (실제: ${JSON.stringify(valueCellText)})`);
}

console.log(`\n총 ${passed + failedCount}건 중 PASS=${passed}, FAIL=${failedCount}`);
process.exit(failedCount > 0 ? 1 : 0);
