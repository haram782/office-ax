/**
 * HWP 표 셀 관련 공용 유틸 — hwp_worker.mjs(치환)와
 * hwp_verify_anchor.mjs(검증 전용)가 함께 사용한다.
 */

/**
 * 표 셀이 비어 있는지(공백뿐인지) 확인한다. 셀이 없거나 조회에 실패하면
 * 비어 있지 않은 것으로 간주해 원래 셀 치환 경로로 폴백한다.
 */
export function cellIsEmpty(doc, sec, parentPara, ctrlIdx, cellIdx) {
  try {
    const paraCount = doc.getCellParagraphCount(sec, parentPara, ctrlIdx, cellIdx);
    if (paraCount < 0) return false;
    for (let p = 0; p < paraCount; p += 1) {
      const text = doc.getTextInCell(sec, parentPara, ctrlIdx, cellIdx, p, 0, 1000) || '';
      if (text.trim()) return false;
    }
    return true;
  } catch {
    return false;
  }
}

/**
 * 라벨 셀(cellIdx) 바로 다음부터 읽기 순서(cellIdx 오름차순 — HWP 표 셀은
 * 행 우선 읽기 순서로 인덱싱된다)로 최대 maxDistance칸까지 스캔해, 처음 나오는
 * 빈 칸의 cellIdx를 찾는다.
 *
 * 기존에는 "바로 옆 칸(cellIdx+1)"만 확인했는데, 실제 정부 공문서 양식은
 * "라벨/열 헤더 행들 + 그 아래 별도의 빈 입력 행" 구조가 흔해서, 값 칸이
 * 라벨로부터 몇 칸 떨어져 있는 경우가 많다(예: "이름" 열 헤더 바로 다음엔
 * "생년월일"·"주소"·"전화번호" 헤더가 더 있고, 그 다음에야 빈 입력 행이 옴).
 * 표 전체(getTableDimensions의 cellCount)를 넘어서는 범위는 스캔하지 않는다.
 *
 * @returns {number | null} 찾은 빈 칸의 cellIdx, 없으면 null
 */
export function findNearestEmptyCellForward(doc, sec, parentPara, ctrlIdx, fromCellIdx, maxDistance = 8) {
  let cellCount = Infinity;
  try {
    const dims = JSON.parse(doc.getTableDimensions(sec, parentPara, ctrlIdx));
    if (Number.isInteger(dims?.cellCount)) cellCount = dims.cellCount;
  } catch { /* 조회 실패 시 상한 없이(위 maxDistance로만 제한) 스캔 */ }

  const limit = Math.min(fromCellIdx + maxDistance, cellCount - 1);
  for (let idx = fromCellIdx + 1; idx <= limit; idx += 1) {
    if (cellIsEmpty(doc, sec, parentPara, ctrlIdx, idx)) return idx;
  }
  return null;
}

/**
 * 매치 1건이 "안전하게 적용 가능한지" 판단한다 — hwp_worker.mjs(실제 치환)와
 * hwp_verify_anchor.mjs(사전 검증)가 반드시 동일한 기준/순서로 판단해야 한다.
 * (과거 두 파일에 이 로직이 각자 복제되어 순서가 어긋났던 버그가 있었다 — 이제
 * 하나의 함수로 공유해 재발을 막는다.)
 *
 *   1. 본문 문단 매치(cellContext 없음)는 그 자리 치환이라 깨질 위험이 없다 → 항상 안전.
 *   2. 표 셀 매치는, replacement가 "원문+추가값" 형태이고 읽기 순서상 가까운
 *      빈 칸을 찾을 수 있으면 → 그 칸에 값만 넣는다(원래 셀은 안 건드리므로
 *      라벨이 조각이든 전체든 항상 안전).
 *   3. 그 경로를 못 타면(추가값이 없거나 근처에 빈 칸이 없으면) → 같은 셀
 *      안에서 매치 위치에 직접 치환한다. 이건 anchor가 셀 내용 전체와
 *      일치할 때만 안전하다 — 라벨 일부만 가리키면 나머지가 쪼개진다.
 */
export function isSafeMatch(doc, match, targetText, replacement) {
  if (!match.cellContext) return true;

  const { parentPara, ctrlIdx, cellIdx, cellPara } = match.cellContext;

  const appendedValue = (replacement || '').startsWith(targetText || '')
    ? (replacement || '').slice((targetText || '').length).trim()
    : '';
  if (appendedValue) {
    const valueCellIdx = findNearestEmptyCellForward(doc, match.sec, parentPara, ctrlIdx, cellIdx);
    if (valueCellIdx !== null) return true;
  }

  let fullCellText = '';
  try {
    fullCellText = doc.getTextInCell(match.sec, parentPara, ctrlIdx, cellIdx, cellPara, 0, 2000) || '';
  } catch {
    return false; // 셀 내용을 못 읽으면 안전 여부를 판단할 수 없으므로 보수적으로 불안전 처리
  }
  const matchedText = fullCellText.slice(match.charOffset, match.charOffset + match.length);
  return fullCellText.trim() === matchedText.trim();
}

/**
 * 매치 목록을 "안전한 매치 우선" 순서로 재정렬한다(안전/불안전 각 그룹 내부의
 * 상대 순서는 유지하는 stable 정렬). occurrence(1-based) 인덱싱이 여러 매치
 * 중 하나를 고를 때, 우연히 안전하지 않은 매치(예: 설명문 속 우연한 동일
 * 텍스트)가 앞서 있어서 그걸 집어버리는 걸 막는다.
 */
export function sortMatchesSafeFirst(doc, matches, targetText, replacement) {
  const withSafety = matches.map((m) => ({ m, safe: isSafeMatch(doc, m, targetText, replacement) }));
  return [
    ...withSafety.filter((x) => x.safe).map((x) => x.m),
    ...withSafety.filter((x) => !x.safe).map((x) => x.m),
  ];
}
