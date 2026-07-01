/**
 * ChangeSuggestionCard — set_cell_style 스타일 요약 표시 테스트.
 * document-format-editing-ax-v1-ko.md 9.2/11.2절 기준.
 */

import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { ChangeSuggestionCard } from '../src/pages/Workspace/ChangeSuggestionCard'

function makeSuggestion(overrides = {}) {
  return {
    id: 'op_style_1',
    source: 'patch_changes',
    format: 'xlsx',
    operation: 'set_cell_style',
    changeType: 'patch',
    severity: 'info',
    title: '표 헤더 서식 정리',
    original: '',
    replacement: '',
    reason: '헤더 영역이 일반 셀처럼 보여 표의 구분이 어렵습니다.',
    anchor: { type: 'cell_range', sheet: 'Sheet1', range: 'A1:D1' },
    patch: {
      font_bold: true,
      fill_color: 'D9EAF7',
      horizontal_alignment: 'center',
      vertical_alignment: 'center',
      border: 'thin',
    },
    changeDbId: 1,
    ...overrides,
  }
}

function renderCard(suggestion, props = {}) {
  return render(
    <ChangeSuggestionCard
      suggestion={suggestion}
      status="pending"
      isSelected={false}
      onSelect={vi.fn()}
      onAccept={vi.fn()}
      onReject={vi.fn()}
      onReset={vi.fn()}
      {...props}
    />
  )
}

describe('ChangeSuggestionCard — set_cell_style', () => {
  it('original/replacement가 비어 있어도 빈 diff 줄을 보여주지 않는다', () => {
    renderCard(makeSuggestion())
    // 기존 diff 줄은 line-through 스타일 span으로 렌더된다 — original이 빈 문자열이므로 없어야 한다
    expect(screen.queryByText('→')).toBeNull()
  })

  it('패치 내용을 사람이 읽을 수 있는 요약 문장으로 표시한다', () => {
    renderCard(makeSuggestion())
    expect(screen.getByText(/굵게/)).toBeTruthy()
    expect(screen.getByText(/배경색 D9EAF7/)).toBeTruthy()
    expect(screen.getByText(/가운데 정렬/)).toBeTruthy()
    expect(screen.getByText(/얇은 테두리/)).toBeTruthy()
  })

  it('range anchor 위치(A1:D1 · Sheet1)를 표시한다', () => {
    renderCard(makeSuggestion())
    expect(screen.getByText('A1:D1 · Sheet1')).toBeTruthy()
  })

  it('제목과 이유는 다른 operation과 동일하게 표시된다', () => {
    renderCard(makeSuggestion())
    expect(screen.getByText('표 헤더 서식 정리')).toBeTruthy()
    expect(screen.getByText('헤더 영역이 일반 셀처럼 보여 표의 구분이 어렵습니다.')).toBeTruthy()
  })

  it('patch 필드가 비어 있으면 스타일 요약 줄을 렌더하지 않는다', () => {
    renderCard(makeSuggestion({ patch: {} }))
    expect(screen.queryByText(/굵게/)).toBeNull()
    expect(screen.queryByText(/배경색/)).toBeNull()
    // reason 줄("헤더 영역이...")은 그대로 표시되어야 한다 — 스타일 요약 줄만 비어야 함
    expect(screen.getByText('헤더 영역이 일반 셀처럼 보여 표의 구분이 어렵습니다.')).toBeTruthy()
  })

  it('대기 상태에서 적용/거절 버튼이 기존과 동일하게 렌더된다', () => {
    renderCard(makeSuggestion())
    expect(screen.getByTitle('적용')).toBeTruthy()
    expect(screen.getByTitle('거절')).toBeTruthy()
  })
})

describe('ChangeSuggestionCard — 기존 replace_cell UI 회귀 확인', () => {
  it('replace_cell suggestion은 여전히 original → replacement diff를 보여준다', () => {
    const suggestion = makeSuggestion({
      id: 'op_replace_1',
      operation: 'replace_cell',
      original: '5,000,000',
      replacement: '6,500,000',
      anchor: { type: 'cell', sheet: 'Sheet1', cell: 'D12' },
      patch: { method: 'openpyxl_set_value', value: '6,500,000' },
    })
    renderCard(suggestion)
    expect(screen.getByText('5,000,000')).toBeTruthy()
    expect(screen.getByText('6,500,000')).toBeTruthy()
    expect(screen.getByText('D12 · Sheet1')).toBeTruthy()
  })
})
