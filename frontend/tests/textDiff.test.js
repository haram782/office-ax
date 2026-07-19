import { describe, it, expect } from 'vitest'
import { diffSegments, diffSegmentsForDisplay } from '../src/utils/textDiff'

describe('diffSegments', () => {
  it('공통 접두사(라벨) 뒤에 값이 붙는 단순한 경우 공통 구간은 그대로, 추가된 부분만 added로 표시한다', () => {
    const segments = diffSegments('주 소', '주 소 분당동 102-1')

    expect(segments.some(s => s.removed)).toBe(false)
    expect(segments.filter(s => !s.added && !s.removed).map(s => s.value).join('')).toBe('주 소')
    expect(segments.filter(s => s.added).map(s => s.value).join('')).toContain('분당동 102-1')
  })

  it('original이 빈 문자열이면 전체가 added다', () => {
    expect(diffSegments('', '새 값')).toEqual([{ value: '새 값', added: true }])
  })

  it('replacement가 빈 문자열이면 전체가 removed다', () => {
    expect(diffSegments('옛 값', '')).toEqual([{ value: '옛 값', removed: true }])
  })

  it('둘 다 비어 있으면 빈 배열을 반환한다', () => {
    expect(diffSegments('', '')).toEqual([])
  })
})

describe('diffSegmentsForDisplay', () => {
  it('[버그 수정] 라벨 뒤에 값이 붙는 단순한 모양은 세밀한 diff를 그대로 쓴다', () => {
    const segments = diffSegmentsForDisplay('주 소', '주 소 분당동 102-1')

    expect(segments.some(s => s.removed)).toBe(false)
    expect(segments.filter(s => !s.added && !s.removed).map(s => s.value).join('')).toBe('주 소')
  })

  it('완전히 다른 값끼리의 교체(숫자 등)는 잘게 쪼개지 않고 전체 교체로 보여준다', () => {
    // jsdiff word diff는 "5,000,000"↔"6,500,000"을 5/6, 000/500 등으로 잘게 쪼개
    // 번갈아 나타나 오히려 읽기 어렵다 — 이런 복잡한 모양은 통째로 교체된 것으로 표시한다.
    const segments = diffSegmentsForDisplay('5,000,000', '6,500,000')

    expect(segments).toEqual([
      { value: '5,000,000', removed: true },
      { value: '6,500,000', added: true },
    ])
  })
})
