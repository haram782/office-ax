/**
 * hwp_search_utils.mjs 단위 테스트 (프로덕션 코드 아님, 순수 함수라 WASM 불필요).
 *
 * 실행: node test_hwp_search_utils.mjs
 */
import { buildWhitespaceWidthVariants, searchAllTextWhitespaceTolerant } from './hwp_search_utils.mjs';

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

test('공백 없는 문자열은 변형 목록이 비어있다', () => {
  assert(buildWhitespaceWidthVariants('채권자').length === 0);
});

test('순수 일반 스페이스 폭 변형이 포함된다 (기존 회귀)', () => {
  const variants = buildWhitespaceWidthVariants('주 소');
  assert(variants.includes('주  소'), '폭 2칸 변형이 있어야 함');
  assert(variants.includes('주   소'), '폭 3칸 변형이 있어야 함');
});

test('[회귀] 실제 HWP 양식에서 관찰된 혼합 공백(일반 스페이스 7칸 + FIGURE SPACE)을 재현한다', () => {
  // 차용증-양식.hwp 셀 원문: "성" + ' '.repeat(7) + ' ' + "명"
  const variants = buildWhitespaceWidthVariants('성 명');
  const expected = '성' + ' '.repeat(7) + ' ' + '명';
  assert(
    variants.includes(expected),
    `혼합 공백 변형이 목록에 있어야 함 (목록 길이: ${variants.length})`
  );
});

test('IDEOGRAPHIC SPACE(U+3000) 혼합 변형도 생성된다', () => {
  const variants = buildWhitespaceWidthVariants('A B');
  assert(variants.includes('A' + ' '.repeat(3) + '　' + 'B'));
});

// ── searchAllTextWhitespaceTolerant는 doc.searchAllText를 흉내낸 mock으로 검증 ──

function makeMockDoc(realText) {
  return {
    searchAllText(query) {
      // 간단 모킹: query가 realText에 정확히 포함될 때만 매치 1건 반환
      if (realText.includes(query)) {
        return JSON.stringify([{ sec: 0, para: 0, charOffset: realText.indexOf(query), length: query.length }]);
      }
      return JSON.stringify([]);
    },
  };
}

test('정확 일치가 안 되면 공백 변형으로 재시도해 혼합 공백도 찾는다', () => {
  const realText = '성' + ' '.repeat(7) + ' ' + '명';
  const doc = makeMockDoc(realText);
  const { matches, usedQuery } = searchAllTextWhitespaceTolerant(doc, '성 명');
  assert(matches.length === 1, '매치 1건이어야 함');
  assert(usedQuery === realText, 'usedQuery가 실제 공백 조합과 일치해야 함');
});

// ── [회귀] 같은 라벨 글자가 서로 다른 공백 폭으로 여러 군데 있는 경우 ───────────
// 실제 사례(자동차멸실인정서신청서.hwp): 안내문 속엔 "성 명"(공백 1칸, 정확
// 일치)이 있고, 진짜 입력 칸 라벨은 "성    명"(공백 4칸, 변형 일치로만
// 찾아짐)이다. 과거 구현은 정확 일치에서 먼저 매치가 나오면 거기서 멈춰
// 변형 재시도를 아예 안 했다 — 진짜 칸을 영원히 놓치는 버그였다.
function makeMockDocWithTwoOccurrences(exactText, variantText) {
  return {
    searchAllText(query) {
      const matches = [];
      if (exactText.includes(query)) {
        matches.push({ sec: 0, para: 0, charOffset: exactText.indexOf(query), length: query.length });
      }
      if (variantText.includes(query)) {
        matches.push({ sec: 0, para: 1, charOffset: variantText.indexOf(query), length: query.length });
      }
      return JSON.stringify(matches);
    },
  };
}

test('[회귀] 정확 일치 매치가 있어도 멈추지 않고, 공백 폭 변형 매치까지 합쳐서 반환한다', () => {
  const exactText = '안내: (성 명)을 적으세요';
  const variantText = '성' + ' '.repeat(4) + '명';
  const doc = makeMockDocWithTwoOccurrences(exactText, variantText);
  const { matches } = searchAllTextWhitespaceTolerant(doc, '성 명');
  assert(matches.length === 2, `정확 일치 1건 + 변형 1건 = 총 2건이어야 함 (실제: ${matches.length})`);
});

console.log(`\n총 ${passed + failed}건 중 PASS=${passed}, FAIL=${failed}`);
if (failed > 0) process.exit(1);
