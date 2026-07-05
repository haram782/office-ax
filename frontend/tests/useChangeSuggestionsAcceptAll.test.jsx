/**
 * useChangeSuggestions — handleAcceptAll 서버 연동 테스트
 * Red → Green → Refactor TDD
 *
 * versionId 유무에 따른 분기, 충돌 자동 반려 결과 반영, 실패 시 미반영, 중복 클릭 방지를 검증한다.
 */

import { renderHook, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockPatch          = vi.fn()
const mockAcceptAll      = vi.hoisted(() => vi.fn())
vi.mock('../src/api/documentChanges', () => ({
  patchDocumentChange: (...args) => mockPatch(...args),
  acceptAllChanges:    (...args) => mockAcceptAll(...args),
}))

import { useChangeSuggestions } from '../src/hooks/useChangeSuggestions'

// changeDbId가 있는 pending 항목 2개
const SNIPPET = {
  edit_suggestions: [
    { id: 's1', title: '항목1', anchor: { type: 'text_match', target_text: '하나' }, changeDbId: 11 },
    { id: 's2', title: '항목2', anchor: { type: 'text_match', target_text: '둘' },   changeDbId: 12 },
  ],
}

describe('useChangeSuggestions — handleAcceptAll (versionId 없음)', () => {
  beforeEach(() => vi.clearAllMocks())

  it('versionId 없으면 로컬 상태만 변경하고 API를 호출하지 않는다', async () => {
    const { result } = renderHook(() => useChangeSuggestions(SNIPPET, null, null))

    await act(async () => { result.current.handleAcceptAll() })

    expect(result.current.statuses['s1']).toBe('applied')
    expect(result.current.statuses['s2']).toBe('applied')
    expect(mockAcceptAll).not.toHaveBeenCalled()
  })
})

describe('useChangeSuggestions — handleAcceptAll (versionId 있음)', () => {
  beforeEach(() => vi.clearAllMocks())

  it('versionId 있으면 acceptAllChanges를 uploadId·versionId로 호출한다', async () => {
    mockAcceptAll.mockResolvedValue({ applied: [], rejected: [] })

    const { result } = renderHook(() => useChangeSuggestions(SNIPPET, 100, 200))

    await act(async () => { await result.current.handleAcceptAll() })

    expect(mockAcceptAll).toHaveBeenCalledWith(100, 200, null)
  })

  it('applied/rejected 응답이 changeDbId 매핑을 통해 statuses에 반영된다', async () => {
    mockAcceptAll.mockResolvedValue({
      applied:  [{ id: 11, status: 'applied' }],
      rejected: [{ id: 12, status: 'rejected', reason: '사유\n[자동 반려: 동일 위치 변경 충돌, 더 높은 신뢰도 변경 채택]' }],
    })

    const { result } = renderHook(() => useChangeSuggestions(SNIPPET, 100, 200))

    await act(async () => { await result.current.handleAcceptAll() })

    expect(result.current.statuses['s1']).toBe('applied')
    expect(result.current.statuses['s2']).toBe('rejected')
  })

  it('자동 반려된 항목은 autoRejectedIds에 포함된다', async () => {
    mockAcceptAll.mockResolvedValue({
      applied:  [{ id: 11, status: 'applied' }],
      rejected: [{ id: 12, status: 'rejected', reason: '사유\n[자동 반려: 동일 위치 변경 충돌, 더 높은 신뢰도 변경 채택]' }],
    })

    const { result } = renderHook(() => useChangeSuggestions(SNIPPET, 100, 200))

    await act(async () => { await result.current.handleAcceptAll() })

    expect(result.current.autoRejectedIds.has('s2')).toBe(true)
    expect(result.current.autoRejectedIds.has('s1')).toBe(false)
  })

  it('API 실패 시 statuses는 변경되지 않고 acceptAllError가 설정된다', async () => {
    mockAcceptAll.mockRejectedValue(new Error('서버 오류'))

    const { result } = renderHook(() => useChangeSuggestions(SNIPPET, 100, 200))

    await act(async () => { await result.current.handleAcceptAll() })

    expect(result.current.statuses['s1']).toBe('pending')
    expect(result.current.statuses['s2']).toBe('pending')
    expect(result.current.acceptAllError).toBeTruthy()
  })

  it('isAcceptingAll true인 동안 재호출되지 않는다 (중복 클릭 방지)', async () => {
    let resolveFn
    mockAcceptAll.mockReturnValue(new Promise(resolve => { resolveFn = resolve }))

    const { result } = renderHook(() => useChangeSuggestions(SNIPPET, 100, 200))

    act(() => { result.current.handleAcceptAll() })
    expect(result.current.isAcceptingAll).toBe(true)

    // 진행 중 재호출 시도 — 무시되어야 한다
    act(() => { result.current.handleAcceptAll() })
    expect(mockAcceptAll).toHaveBeenCalledTimes(1)

    await act(async () => { resolveFn({ applied: [], rejected: [] }) })
    expect(result.current.isAcceptingAll).toBe(false)
  })
})
