/**
 * hwp_verify_anchor.mjs 검증용 probe 스크립트 (프로덕션 코드 아님).
 *
 * 실행: node test_hwp_verify_anchor.mjs
 */
import { readFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';

const SAMPLE_PATH = new URL('../apps/documents/fixtures/sample.hwp', import.meta.url);

let passed = 0;
let failed = 0;

function test(name, fn) {
  try {
    fn();
    console.log(`  PASS: ${name}`);
    passed += 1;
  } catch (err) {
    console.error(`  FAIL: ${name}`);
    console.error(`    ${err.message}`);
    failed += 1;
  }
}

function assert(cond, msg) {
  if (!cond) throw new Error(msg || 'assertion failed');
}

function runVerify(hwpBytes, anchors) {
  const payload = {
    input_b64: Buffer.from(hwpBytes).toString('base64'),
    anchors,
  };
  const result = spawnSync('node', ['hwp_verify_anchor.mjs'], {
    input: JSON.stringify(payload),
    encoding: 'utf-8',
    cwd: new URL('.', import.meta.url).pathname,
  });
  if (result.status !== 0) {
    throw new Error(`verify worker exited ${result.status}: ${result.stderr}`);
  }
  return JSON.parse(result.stdout);
}

const sampleBytes = readFileSync(SAMPLE_PATH);
const LOAN_FORM_PATH = new URL('../../sample-docs/차용증-양식.hwp', import.meta.url);
const loanFormBytes = readFileSync(LOAN_FORM_PATH);
const POWER_OF_ATTORNEY_PATH = new URL('../../scripts/eval_docs/위임장.hwp', import.meta.url);
const powerOfAttorneyBytes = readFileSync(POWER_OF_ATTORNEY_PATH);
const VEHICLE_EXTINCTION_PATH = new URL('../../scripts/eval_docs/자동차멸실인정서신청서.hwp', import.meta.url);
const vehicleExtinctionBytes = readFileSync(VEHICLE_EXTINCTION_PATH);

test('문서에 실제로 있는 텍스트는 found=true, match_count>=1', () => {
  const { results } = runVerify(sampleBytes, [
    { operation_id: 'op_1', target_text: '테스트' },
  ]);
  assert(results.length === 1, `결과 1건이어야 함 (실제: ${results.length})`);
  assert(results[0].found === true, 'found가 true여야 함');
  assert(results[0].match_count >= 1, 'match_count가 1 이상이어야 함');
});

test('문서에 없는 텍스트는 found=false, match_count=0', () => {
  const { results } = runVerify(sampleBytes, [
    { operation_id: 'op_2', target_text: '존재하지않는문구절대없음XYZ' },
  ]);
  assert(results[0].found === false, 'found가 false여야 함');
  assert(results[0].match_count === 0, 'match_count가 0이어야 함');
});

test('anchor 여러 개를 한 번에 검증할 수 있다', () => {
  const { results } = runVerify(sampleBytes, [
    { operation_id: 'op_a', target_text: '테스트' },
    { operation_id: 'op_b', target_text: '없는텍스트123' },
  ]);
  assert(results.length === 2, '결과가 2건이어야 함');
  const byId = Object.fromEntries(results.map((r) => [r.operation_id, r]));
  assert(byId.op_a.found === true, 'op_a는 found=true');
  assert(byId.op_b.found === false, 'op_b는 found=false');
});

test('원본을 수정하지 않는다 (읽기 전용) — 같은 입력으로 반복 호출해도 결과가 동일하다', () => {
  const first = runVerify(sampleBytes, [{ operation_id: 'op_1', target_text: '테스트' }]);
  const second = runVerify(sampleBytes, [{ operation_id: 'op_1', target_text: '테스트' }]);
  assert(
    first.results[0].match_count === second.results[0].match_count,
    '반복 호출 결과(match_count)가 동일해야 한다 — 상태를 변경하지 않는다는 뜻'
  );
});

// ── [회귀] 라벨 조각 anchor 안전성 검사 — 실제 차용증-양식.hwp로 재현 ────────────
// 실제 셀 원문: "성" + 공백 7칸 + FIGURE SPACE + "명" (하나의 셀)

test('[회귀] 라벨 전체("성  명")를 anchor로 쓰면 안전(found=true)하다', () => {
  const { results } = runVerify(loanFormBytes, [
    { operation_id: 'op_full', target_text: '성 명', replacement: '성 명 박하람' },
  ]);
  assert(results[0].found === true, `전체 라벨 매치는 안전해야 함 (실제: ${JSON.stringify(results[0])})`);
});

test('[회귀] 라벨 조각("성")만 anchor로 쓰고 replacement도 없으면 불안전(found=false)하다', () => {
  const { results } = runVerify(loanFormBytes, [
    { operation_id: 'op_frag', target_text: '성' },
  ]);
  assert(results[0].found === false, '라벨 조각 단독 매치는 불안전해야 함');
  assert(results[0].reason === 'fragment_match_unsafe', `reason이 fragment_match_unsafe여야 함 (실제: ${results[0].reason})`);
});

test('[회귀] 라벨 조각("성")에 "원문+값"(추가 형태) replacement를 주면, 근처 빈 칸을 찾아 안전해진다', () => {
  // original을 "성" 한 글자만 가리켜도, replacement가 "성 박하람"처럼 원문으로
  // 시작하면 읽기 순서상 가까운 빈 칸(라벨 셀 자체를 건드리지 않음)을 찾아
  // 적용하므로 안전하다 — hwp_worker.mjs의 실제 치환 우선순위와 일치해야 한다.
  const { results } = runVerify(loanFormBytes, [
    { operation_id: 'op_frag2', target_text: '성', replacement: '성 박하람' },
  ]);
  assert(results[0].found === true, `근처 빈 칸으로 라우팅되어 안전해야 함 (실제: ${JSON.stringify(results[0])})`);
});

test('[회귀] 라벨 조각("성")에 원문으로 시작하지 않는 replacement(추가가 아닌 치환)를 주면 여전히 불안전하다', () => {
  // appendedValue가 비어있으면(원문 추가 패턴이 아니면) 근처 빈 칸을 찾지 않고
  // 매치 위치에 직접 치환하므로, 라벨 조각 매치는 여전히 위험하다.
  const { results } = runVerify(loanFormBytes, [
    { operation_id: 'op_frag3', target_text: '성', replacement: '완전히 다른 값' },
  ]);
  assert(results[0].found === false, '추가 패턴이 아닌 라벨 조각 치환은 여전히 불안전해야 함');
  assert(results[0].reason === 'fragment_match_unsafe', `reason이 fragment_match_unsafe여야 함 (실제: ${results[0].reason})`);
});

// ── [회귀] 열 헤더 행 + 별도의 빈 입력 행 구조(위임장.hwp) ─────────────────────

test('[회귀] 라벨/값이 바로 옆 칸이 아니라 몇 칸 떨어진 빈 입력 행에 있어도 안전하다', () => {
  // 위임장.hwp: "이름"(열 헤더, cellIdx=4) 다음에 "생년월일"·"주소"·"전화번호"
  // 헤더가 더 있고, 그 다음에야 공용 빈 입력 행(cellIdx=8)이 온다.
  const { results } = runVerify(powerOfAttorneyBytes, [
    { operation_id: 'op_name', target_text: '이름', replacement: '이름 박하람' },
  ]);
  assert(results[0].found === true, `몇 칸 떨어진 빈 입력 행도 찾아야 함 (실제: ${JSON.stringify(results[0])})`);
});

// ── [회귀] 같은 라벨 글자가 안내문 속에도 우연히 있는 문서(자동차멸실인정서신청서.hwp) ──
// 안내문 속 "성 명"(공백 1칸, 정확 일치지만 값 넣을 빈 칸이 없어 불안전)이
// 먼저 매치되어도, 진짜 입력 칸 라벨("성    명", 공백 4칸, 변형 일치)을
// 찾아 안전하다고 판단해야 한다.

test('[회귀] 안내문 속 우연한 동일 라벨이 먼저 매치돼도, 폭 변형으로 찾아지는 진짜 입력 칸이 있으면 안전하다', () => {
  const { results } = runVerify(vehicleExtinctionBytes, [
    { operation_id: 'op_vehicle', target_text: '성 명', replacement: '성 명 박하람' },
  ]);
  assert(results[0].found === true, `진짜 입력 칸을 찾아 안전해야 함 (실제: ${JSON.stringify(results[0])})`);
});

console.log(`\n총 ${passed + failed}건 중 PASS=${passed}, FAIL=${failed}`);
if (failed > 0) process.exit(1);
