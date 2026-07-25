import { diffWordsWithSpace } from 'diff'

/**
 * original → replacement 사이의 word 단위 diff. jsdiff의 Change 객체
 * ({ value, added, removed })를 그대로 반환한다.
 */
export function diffSegments(original, replacement) {
  if (!original) return replacement ? [{ value: replacement, added: true }] : []
  if (!replacement) return [{ value: original, removed: true }]
  return diffWordsWithSpace(original, replacement)
}

/**
 * 화면 표시용 diff.
 *
 * jsdiff의 세밀한 word 단위 diff는 완전히 다른 값을 비교할 때(예: "5,000,000" →
 * "6,500,000") 우연히 흩어진 공통 문자(쉼표 등) 때문에 취소선/하이라이트가 잘게
 * 쪼개져 번갈아 나타나 오히려 읽기 어려워진다. "공통 구간 최대 1번 + 변경 구간"
 * 처럼 단순한 모양(라벨 뒤에 값이 붙는 경우 등)일 때만 세밀한 diff를 쓰고, 그보다
 * 복잡하면(값 자체가 통째로 바뀐 경우) 기존처럼 original 전체 → replacement
 * 전체로 보여준다.
 */
export function diffSegmentsForDisplay(original, replacement) {
  const segments = diffSegments(original, replacement)

  const removedRuns = segments.filter(s => s.removed).length
  const addedRuns = segments.filter(s => s.added).length
  const isSimpleShape = removedRuns <= 1 && addedRuns <= 1

  if (isSimpleShape) return segments

  const whole = []
  if (original) whole.push({ value: original, removed: true })
  if (replacement) whole.push({ value: replacement, added: true })
  return whole
}
