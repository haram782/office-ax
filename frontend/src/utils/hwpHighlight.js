/**
 * HWP 뷰어의 text_match 하이라이트 rect 계산.
 *
 * doc은 @rhwp/core HwpDocument 인터페이스(searchAllText/getSelectionRects)를
 * 만족하는 객체다 — WASM 없이 fake 객체로 테스트할 수 있도록 분리했다.
 */

/**
 * original → replacement에서 새로 추가된 구간의 replacement 내 [start, end) 위치.
 * 공통 접두사/접미사를 제외한 나머지가 추가 구간이며, 가장자리 공백은 하이라이트
 * 박스가 불필요하게 넓어지지 않도록 잘라낸다. 추가된 게 없으면 null.
 */
export function addedRangeInReplacement(original = '', replacement = '') {
  if (!replacement || original === replacement) return null

  let prefix = 0
  const maxPrefix = Math.min(original.length, replacement.length)
  while (prefix < maxPrefix && original[prefix] === replacement[prefix]) prefix += 1

  let suffix = 0
  const maxSuffix = Math.min(original.length, replacement.length) - prefix
  while (
    suffix < maxSuffix &&
    original[original.length - 1 - suffix] === replacement[replacement.length - 1 - suffix]
  ) suffix += 1

  let start = prefix
  let end = replacement.length - suffix
  while (start < end && /\s/.test(replacement[start])) start += 1
  while (end > start && /\s/.test(replacement[end - 1])) end -= 1
  if (end <= start) return null
  return { start, end }
}

function searchMatches(doc, query) {
  try {
    const parsed = JSON.parse(doc.searchAllText(query, false, true))
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

/**
 * 하이라이트 1건의 문서 좌표 rect 목록을 계산한다.
 *
 * 적용된(applied) 변경을 반영본 뷰에서 볼 때는 문서에 replacement가 실제로
 * 존재한다 — 이때는 anchor 원본(라벨)이 아니라 새로 추가된 값 부분만
 * 하이라이트해야 의미가 맞다. replacement가 문서에 없으면(원본 뷰의 pending
 * 제안) 기존대로 target_text 위치를 하이라이트한다.
 *
 * @returns {Array<{ pageIndex, x, y, width, height }>}
 */
export function computeHighlightRects(doc, highlight) {
  const anchor = highlight.anchor ?? {}
  const targetText = anchor.target_text || anchor.text_match || highlight.original || ''
  const replacement = highlight.replacement || ''

  let match = null
  let charOffset, length

  // 1차: replacement가 문서에 있으면 추가된 부분만 하이라이트.
  // replacement는 구체적인 긴 문자열이라 첫 매치만 쓴다.
  if (replacement) {
    const [m] = searchMatches(doc, replacement)
    if (m) {
      match = m
      const range = addedRangeInReplacement(targetText, replacement)
      if (range) {
        charOffset = m.charOffset + range.start
        length = range.end - range.start
      } else {
        charOffset = m.charOffset
        length = m.length ?? replacement.length
      }
    }
  }

  // 2차: 값이 라벨 옆 빈 셀에 단독으로 들어간 경우(라벨/값 셀 쌍 구조) —
  // replacement 전체는 문서에 연속으로 존재하지 않으므로 추가된 값 부분만 직접 찾는다.
  if (!match && replacement) {
    const range = addedRangeInReplacement(targetText, replacement)
    if (range) {
      const addedText = replacement.slice(range.start, range.end)
      const [m] = searchMatches(doc, addedText)
      if (m) {
        match = m
        charOffset = m.charOffset
        length = m.length ?? addedText.length
      }
    }
  }

  // 3차: 기존 동작 — target_text의 occurrence번째 매치를 하이라이트
  if (!match) {
    if (!targetText) return []
    const occurrence = Number.isInteger(anchor.occurrence) && anchor.occurrence > 0
      ? anchor.occurrence
      : 1
    const matches = searchMatches(doc, targetText)
    if (matches.length < occurrence) return []
    match = matches[occurrence - 1]
    charOffset = match.charOffset
    length = match.length ?? targetText.length
  }

  // 표 셀 내부 매치는 본문 좌표계가 아니라 셀 좌표계 API로 rect를 구해야 한다 —
  // match.para는 표 컨트롤을 담는 (대개 빈) 본문 문단이라 엉뚱한 위치가 나온다.
  try {
    let rects
    if (match.cellContext) {
      const { parentPara, ctrlIdx, cellIdx, cellPara } = match.cellContext
      rects = JSON.parse(
        doc.getSelectionRectsInCell(
          match.sec, parentPara, ctrlIdx, cellIdx,
          cellPara, charOffset, cellPara, charOffset + length,
        ),
      )
    } else {
      rects = JSON.parse(
        doc.getSelectionRects(match.sec, match.para, charOffset, match.para, charOffset + length),
      )
    }
    if (!Array.isArray(rects)) return []
    return rects.filter(r => r.pageIndex != null && r.x != null && r.y != null)
  } catch {
    return []
  }
}
