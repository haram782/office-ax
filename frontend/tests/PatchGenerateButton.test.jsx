/**
 * 수정본 생성 버튼 렌더링 조건 테스트 — ChangeSummaryBar 통합
 * Red → Green → Refactor TDD
 */

import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ChangeSummaryBar } from '../src/pages/Workspace/ChangeSummaryBar'

// applied 항목 수·uploadId·versionId를 조합한 props 생성 헬퍼
function makeProps({
  appliedCount = 0,
  uploadId     = null,
  versionId    = null,
  patchStatus  = null,
  onPatch      = null,
} = {}) {
  const suggestions = [
    { id: 's1', status: 'pending' },
    { id: 's2', status: 'pending' },
  ]
  const statuses = {
    s1: appliedCount >= 1 ? 'applied' : 'pending',
    s2: appliedCount >= 2 ? 'applied' : 'pending',
  }
  return { suggestions, statuses, onAcceptAll: vi.fn(), uploadId, versionId, patchStatus, onPatch }
}

describe('ChangeSummaryBar — 수정본 생성 버튼', () => {
  beforeEach(() => vi.clearAllMocks())

  it('applied 제안이 없으면 버튼이 렌더되지 않는다', () => {
    render(<ChangeSummaryBar {...makeProps({ appliedCount: 0, uploadId: 1, versionId: 1, onPatch: vi.fn() })} />)
    expect(screen.queryByText('수정본 생성')).toBeNull()
  })

  it('uploadId가 없으면 버튼이 렌더되지 않는다', () => {
    render(<ChangeSummaryBar {...makeProps({ appliedCount: 1, uploadId: null, versionId: 1, onPatch: vi.fn() })} />)
    expect(screen.queryByText('수정본 생성')).toBeNull()
  })

  it('versionId가 없으면 버튼이 렌더되지 않는다', () => {
    render(<ChangeSummaryBar {...makeProps({ appliedCount: 1, uploadId: 1, versionId: null, onPatch: vi.fn() })} />)
    expect(screen.queryByText('수정본 생성')).toBeNull()
  })

  it('applied > 0이고 uploadId·versionId가 있으면 버튼이 렌더된다', () => {
    render(<ChangeSummaryBar {...makeProps({ appliedCount: 1, uploadId: 1, versionId: 2, onPatch: vi.fn() })} />)
    expect(screen.getByText('수정본 생성')).toBeTruthy()
  })

  it('버튼 클릭 시 onPatch가 호출된다', () => {
    const onPatch = vi.fn()
    render(<ChangeSummaryBar {...makeProps({ appliedCount: 1, uploadId: 1, versionId: 2, onPatch })} />)
    fireEvent.click(screen.getByText('수정본 생성'))
    expect(onPatch).toHaveBeenCalledTimes(1)
  })

  it('patchStatus generating이면 버튼이 비활성화된다', () => {
    render(<ChangeSummaryBar {...makeProps({ appliedCount: 1, uploadId: 1, versionId: 2, patchStatus: 'generating', onPatch: vi.fn() })} />)
    // 로딩 중 텍스트 혹은 disabled 버튼 확인
    const btn = screen.getByRole('button', { name: /수정본/ })
    expect(btn.disabled).toBe(true)
  })

  it('patchStatus ready이면 "수정본 생성됨" 텍스트가 표시된다', () => {
    render(<ChangeSummaryBar {...makeProps({ appliedCount: 1, uploadId: 1, versionId: 2, patchStatus: 'ready', onPatch: vi.fn() })} />)
    expect(screen.getByText('수정본 생성됨')).toBeTruthy()
  })

  it('patchStatus failed이면 "생성 실패" 텍스트가 표시된다', () => {
    render(<ChangeSummaryBar {...makeProps({ appliedCount: 1, uploadId: 1, versionId: 2, patchStatus: 'failed', onPatch: vi.fn() })} />)
    expect(screen.getByText(/생성 실패/)).toBeTruthy()
  })
})
