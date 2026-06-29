/**
 * useChangeSuggestions — API 연동 동작 테스트
 * Red → Green → Refactor TDD
 *
 * 낙관적 UI (로컬 즉시 반영) + API 호출 + 실패 시 롤백 검증
 */

import { renderHook, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

// patchDocumentChange 모킹 — 훅이 import하는 경로와 동일
const mockPatch = vi.fn()
vi.mock('../src/api/documentChanges', () => ({
  patchDocumentChange: (...args) => mockPatch(...args),
}))

import { useChangeSuggestions } from '../src/hooks/useChangeSuggestions'

// changeDbId 없는 snippetData — 로컬 상태만 변경 경로
const SNIPPET_NO_DB_ID = {
  edit_suggestions: [{
    id: 's1',
    title: '교정 항목',
    anchor: { type: 'text_match', target_text: '안녕' },
    // changeDbId 없음
  }],
}

// changeDbId 있는 snippetData — BE 연결 경로
const SNIPPET_WITH_DB_ID = {
  edit_suggestions: [{
    id: 's1',
    title: '교정 항목',
    anchor: { type: 'text_match', target_text: '안녕' },
    changeDbId: 42,
  }],
}

describe('useChangeSuggestions — changeDbId 없는 경우', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('handleSetStatus가 로컬 상태만 변경하고 API를 호출하지 않는다', async () => {
    const { result } = renderHook(() => useChangeSuggestions(SNIPPET_NO_DB_ID))

    await act(async () => {
      result.current.handleSetStatus('s1', 'applied')
    })

    expect(result.current.statuses['s1']).toBe('applied')
    expect(mockPatch).not.toHaveBeenCalled()
  })
})

describe('useChangeSuggestions — changeDbId 있는 경우', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('handleSetStatus가 낙관적으로 로컬 상태를 즉시 업데이트한다', async () => {
    mockPatch.mockResolvedValue({ id: 42, status: 'applied' })

    const { result } = renderHook(() => useChangeSuggestions(SNIPPET_WITH_DB_ID))

    await act(async () => {
      result.current.handleSetStatus('s1', 'applied')
    })

    expect(result.current.statuses['s1']).toBe('applied')
  })

  it('patchDocumentChange를 changeDbId와 nextStatus로 호출한다', async () => {
    mockPatch.mockResolvedValue({ id: 42, status: 'applied' })

    const { result } = renderHook(() => useChangeSuggestions(SNIPPET_WITH_DB_ID))

    await act(async () => {
      result.current.handleSetStatus('s1', 'applied')
    })

    expect(mockPatch).toHaveBeenCalledWith(42, 'applied')
  })

  it('API 실패 시 로컬 상태를 이전 값(pending)으로 롤백한다', async () => {
    mockPatch.mockRejectedValue(new Error('서버 오류'))

    const { result } = renderHook(() => useChangeSuggestions(SNIPPET_WITH_DB_ID))

    // 초기 상태 확인
    expect(result.current.statuses['s1']).toBe('pending')

    await act(async () => {
      result.current.handleSetStatus('s1', 'applied')
    })

    // 낙관적 적용 후 실패 → 롤백 → pending
    expect(result.current.statuses['s1']).toBe('pending')
  })

  it('API 호출 중 pendingIds에 해당 id가 포함된다', async () => {
    // 해결되지 않는 promise로 pending 상태 유지
    let resolveFn
    mockPatch.mockReturnValue(new Promise(resolve => { resolveFn = resolve }))

    const { result } = renderHook(() => useChangeSuggestions(SNIPPET_WITH_DB_ID))

    act(() => {
      result.current.handleSetStatus('s1', 'applied')
    })

    // resolve 전에 pendingIds 확인
    expect(result.current.pendingIds.has('s1')).toBe(true)

    // promise 해결 후 pendingIds에서 제거됨
    await act(async () => { resolveFn({ id: 42, status: 'applied' }) })
    expect(result.current.pendingIds.has('s1')).toBe(false)
  })
})
