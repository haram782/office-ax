/**
 * HWP 문서 내 텍스트 검색 공용 유틸 — hwp_worker.mjs(치환)와
 * hwp_verify_anchor.mjs(검증 전용)가 함께 사용한다.
 */

// HWP 양식 문서가 라벨 정렬에 흔히 쓰는, 일반 스페이스(U+0020)와 겉보기엔 구분이
// 안 되는 공백류 문자들. 실제 샘플 문서(차용증-양식.hwp)에서 "성<공백 7칸 +
// U+2007>명"처럼 "N칸의 일반 스페이스 + 폭 고정용 특수 공백 1개"로 끝나는 혼합
// 조합이 관찰됐다 — 순수 반복 문자만으로는 재현할 수 없다.
//   U+00A0 NO-BREAK SPACE, U+2007 FIGURE SPACE(숫자 폭 고정),
//   U+3000 IDEOGRAPHIC SPACE(전각 공백, 한글 문서 정렬에 흔함)
const _ALT_SPACE_CHARS = [' ', ' ', '　'];

/**
 * hwp_text_extract.mjs의 normalizeText()가 연속 공백을 1칸으로 뭉개서 LLM에게
 * 보여주므로, PatchPlan의 original은 실제 문서보다 공백이 적은 형태로 생성될
 * 수 있다(예: 문서엔 "주  소"(2칸)인데 original은 "주 소"(1칸)). 정확 일치
 * 검색이 실패하면, original의 공백런(run)마다 아래 두 형태로 바꿔가며 재시도한다:
 *   1. 일반 스페이스만 폭 1~maxWidth칸
 *   2. 일반 스페이스 1~maxWidth칸 뒤에 폭-고정용 공백류 문자 1개를 덧붙인 조합
 * @param {string} original
 * @returns {string[]} original 자신을 제외한 공백-폭 변형 목록(중복 제거)
 */
export function buildWhitespaceWidthVariants(original, maxWidth = 10) {
  const parts = original.split(/(\s+)/);
  const gapIndices = [];
  parts.forEach((p, i) => { if (/^\s+$/.test(p)) gapIndices.push(i); });
  if (gapIndices.length === 0) return [];

  const gapCandidates = [];
  for (let w = 1; w <= maxWidth; w += 1) gapCandidates.push(' '.repeat(w));
  for (const alt of _ALT_SPACE_CHARS) {
    for (let w = 1; w <= maxWidth; w += 1) gapCandidates.push(' '.repeat(w) + alt);
  }

  // 조합 폭발 방지 — 공백런이 많아도 시도 횟수를 상한선 안으로 제한한다.
  const maxCombos = 400;
  let combos = [[]];
  outer:
  for (let g = 0; g < gapIndices.length; g += 1) {
    const next = [];
    for (const combo of combos) {
      for (const cand of gapCandidates) {
        next.push([...combo, cand]);
        if (next.length >= maxCombos) break outer;
      }
    }
    combos = next;
  }

  const variants = new Set();
  for (const combo of combos) {
    const p = [...parts];
    gapIndices.forEach((idx, k) => { p[idx] = combo[k]; });
    const variant = p.join('');
    if (variant !== original) variants.add(variant);
  }
  return [...variants];
}

/**
 * doc.searchAllText를 원본 그대로 먼저 시도하고, 공백 폭 변형들도 모두
 * 시도해서 매치를 전부 합쳐 반환한다.
 *
 * 과거에는 "원본 그대로"에서 매치가 1건이라도 나오면 거기서 멈췄는데, 실제
 * 문서에는 같은 라벨 글자가 서로 다른 공백 폭으로 여러 군데(예: 진짜 입력
 * 칸 라벨은 공백 4칸, 안내문 속 괄호 설명은 공백 1칸) 나타날 수 있다. 이때
 * 먼저 매치되는 쪽이 하필 안내문(값 넣을 빈 칸이 없는 안전하지 않은 위치)이면,
 * 진짜 입력 칸은 폭 변형 재시도 자체가 실행되지 않아 영원히 찾지 못한다.
 * 그래서 매치가 나온 뒤에도 멈추지 않고 모든 후보 쿼리의 매치를 합쳐
 * 반환하고, 그중 안전한 매치를 고르는 판단은 호출자(hwp_worker.mjs /
 * hwp_verify_anchor.mjs)의 안전성 정렬 로직에 맡긴다.
 * @returns {{ matches: any[], usedQuery: string }} usedQuery는 매치가 처음
 *   나온 후보(로그 표시용) — 실제 선택은 호출자가 matches 전체를 본다.
 */
export function searchAllTextWhitespaceTolerant(doc, original) {
  const tryQuery = (query) => {
    try {
      const parsed = JSON.parse(doc.searchAllText(query, false, true));
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  };

  const allMatches = [];
  let usedQuery = original;
  let foundAny = false;

  const exact = tryQuery(original);
  if (exact.length > 0) {
    allMatches.push(...exact);
    usedQuery = original;
    foundAny = true;
  }

  for (const variant of buildWhitespaceWidthVariants(original)) {
    const matches = tryQuery(variant);
    if (matches.length > 0) {
      allMatches.push(...matches);
      if (!foundAny) usedQuery = variant;
      foundAny = true;
    }
  }

  return { matches: allMatches, usedQuery };
}
