import { describe, it, expect } from 'vitest'
import { addedRangeInReplacement, computeHighlightRects } from '../src/utils/hwpHighlight'

// @rhwp/core HwpDocument의 검색/선택영역 API만 흉내내는 fake.
// bodyText(본문)와 cellText(표 셀 내부)에서 실제로 검색하고, 두 좌표계 API 호출을
// 각각 기록해 어느 구간이 어느 API로 하이라이트됐는지 검증할 수 있게 한다.
function makeFakeDoc(bodyText, cellText = '') {
  const calls = []
  const cellCalls = []
  return {
    calls,
    cellCalls,
    searchAllText(query, _caseSensitive, includeCells) {
      const matches = []
      let idx = bodyText.indexOf(query)
      while (idx !== -1) {
        matches.push({ sec: 0, para: 0, charOffset: idx, length: query.length })
        idx = bodyText.indexOf(query, idx + 1)
      }
      if (includeCells && cellText) {
        let cIdx = cellText.indexOf(query)
        while (cIdx !== -1) {
          matches.push({
            sec: 0, para: 2, charOffset: cIdx, length: query.length,
            cellContext: { parentPara: 2, ctrlIdx: 0, cellIdx: 0, cellPara: 0 },
          })
          cIdx = cellText.indexOf(query, cIdx + 1)
        }
      }
      return JSON.stringify(matches)
    },
    getSelectionRects(sec, para, startOffset, _endPara, endOffset) {
      calls.push({ sec, para, startOffset, endOffset })
      return JSON.stringify([{ pageIndex: 0, x: startOffset, y: 0, width: endOffset - startOffset, height: 10 }])
    },
    getSelectionRectsInCell(sec, parentPara, ctrlIdx, cellIdx, _startCellPara, startOffset, _endCellPara, endOffset) {
      cellCalls.push({ sec, parentPara, ctrlIdx, cellIdx, startOffset, endOffset })
      return JSON.stringify([{ pageIndex: 0, x: startOffset, y: 0, width: endOffset - startOffset, height: 10 }])
    },
  }
}

describe('addedRangeInReplacement', () => {
  it('라벨 뒤에 값이 붙는 경우, 추가된 값 구간만 반환한다 (가장자리 공백 제외)', () => {
    const range = addedRangeInReplacement('주 소', '주 소 분당동 102-1')
    expect('주 소 분당동 102-1'.slice(range.start, range.end)).toBe('분당동 102-1')
  })

  it('완전히 같은 문자열이면 null을 반환한다', () => {
    expect(addedRangeInReplacement('같음', '같음')).toBeNull()
  })

  it('replacement가 비어 있으면 null을 반환한다', () => {
    expect(addedRangeInReplacement('원본', '')).toBeNull()
  })

  it('공통 부분이 없으면 replacement 전체를 반환한다', () => {
    const range = addedRangeInReplacement('AAA', 'BBB')
    expect('BBB'.slice(range.start, range.end)).toBe('BBB')
  })
})

describe('computeHighlightRects', () => {
  it('[버그 수정] 반영본에 replacement가 존재하면 라벨이 아니라 새로 추가된 값 구간을 하이라이트한다', () => {
    // 반영본: "주 소 분당동 102-1"이 실제 본문에 존재
    const doc = makeFakeDoc('주  소 TEL FAX 주 소 분당동 102-1 문서번호')
    const highlight = {
      id: 'h1',
      original: '주 소',
      replacement: '주 소 분당동 102-1',
      anchor: { type: 'text_match', target_text: '주 소' },
    }

    const rects = computeHighlightRects(doc, highlight)

    expect(rects.length).toBe(1)
    const call = doc.calls[0]
    const body = '주  소 TEL FAX 주 소 분당동 102-1 문서번호'
    // 하이라이트된 구간이 정확히 "분당동 102-1"이어야 한다 — 라벨("주 소")이면 버그
    expect(body.slice(call.startOffset, call.endOffset)).toBe('분당동 102-1')
  })

  it('원본 뷰(replacement가 문서에 없음)에서는 기존대로 target_text를 하이라이트한다', () => {
    const doc = makeFakeDoc('주 소 TEL FAX 문서번호')
    const highlight = {
      id: 'h2',
      original: '주 소',
      replacement: '주 소 분당동 102-1',
      anchor: { type: 'text_match', target_text: '주 소' },
    }

    const rects = computeHighlightRects(doc, highlight)

    expect(rects.length).toBe(1)
    const call = doc.calls[0]
    expect(call.startOffset).toBe(0)
    expect(call.endOffset).toBe('주 소'.length)
  })

  it('anchor.occurrence가 있으면 그 번째 매치를 하이라이트한다 (fallback 경로)', () => {
    const doc = makeFakeDoc('사원 A 사원 B 사원 C')
    const highlight = {
      id: 'h3',
      original: '사원',
      replacement: '',
      anchor: { type: 'text_match', target_text: '사원', occurrence: 2 },
    }

    const rects = computeHighlightRects(doc, highlight)

    expect(rects.length).toBe(1)
    expect(doc.calls[0].startOffset).toBe('사원 A '.length)
  })

  it('[버그 수정] 표 셀 내부에 반영된 replacement는 셀 좌표계 API로 하이라이트한다', () => {
    // 셀 내부 치환(케이스: 공문서 라벨 셀) 후에는 replacement가 표 셀 안에만 있다 —
    // 본문 좌표계 getSelectionRects를 쓰면 (빈) 본문 문단 기준의 엉뚱한 위치에 박스가 그려진다.
    const doc = makeFakeDoc('본문 텍스트', '주 소 분당동 102-1')
    const highlight = {
      id: 'h5',
      original: '주 소',
      replacement: '주 소 분당동 102-1',
      anchor: { type: 'text_match', target_text: '주 소' },
    }

    const rects = computeHighlightRects(doc, highlight)

    expect(rects.length).toBe(1)
    expect(doc.calls.length).toBe(0)
    expect(doc.cellCalls.length).toBe(1)
    const call = doc.cellCalls[0]
    expect('주 소 분당동 102-1'.slice(call.startOffset, call.endOffset)).toBe('분당동 102-1')
  })

  it('target_text도 replacement도 못 찾으면 빈 배열을 반환한다', () => {
    const doc = makeFakeDoc('아무 관련 없는 본문')
    const highlight = {
      id: 'h4',
      original: '없는텍스트',
      replacement: '역시없는텍스트',
      anchor: { type: 'text_match', target_text: '없는텍스트' },
    }

    expect(computeHighlightRects(doc, highlight)).toEqual([])
  })
})
