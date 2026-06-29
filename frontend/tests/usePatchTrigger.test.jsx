/**
 * usePatchTrigger 훅 단위 테스트
 * Red → Green → Refactor TDD
 */

import { renderHook, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

// triggerPatch 모킹 — vi.hoisted로 호이스팅 이슈 방지
const mockTriggerPatch = vi.hoisted(() => vi.fn())
vi.mock('../src/api/documentChanges', () => ({
  patchDocumentChange: vi.fn(),
  triggerPatch: (...args) => mockTriggerPatch(...args),
}))

import { usePatchTrigger } from '../src/hooks/usePatchTrigger'

describe('usePatchTrigger', () => {
  beforeEach(() => vi.clearAllMocks())

  it('초기 patchStatus는 null이다', () => {
    const { result } = renderHook(() => usePatchTrigger(1, 2))
    expect(result.current.patchStatus).toBeNull()
  })

  it('trigger 호출 시 triggerPatch API가 uploadId·versionId로 호출된다', async () => {
    mockTriggerPatch.mockResolvedValue({ version_id: 2, status: 'generating' })

    const { result } = renderHook(() => usePatchTrigger(10, 20))

    await act(async () => { await result.current.trigger() })

    expect(mockTriggerPatch).toHaveBeenCalledWith(10, 20)
  })

  it('triggerPatch 성공 시 patchStatus가 generating이 된다', async () => {
    mockTriggerPatch.mockResolvedValue({ version_id: 2, status: 'generating' })

    const { result } = renderHook(() => usePatchTrigger(1, 2))

    await act(async () => { await result.current.trigger() })

    expect(result.current.patchStatus).toBe('generating')
  })

  it('triggerPatch 실패 시 patchStatus가 failed가 된다', async () => {
    mockTriggerPatch.mockRejectedValue(new Error('서버 오류'))

    const { result } = renderHook(() => usePatchTrigger(1, 2))

    await act(async () => { result.current.trigger() })

    await vi.waitFor(() => {
      expect(result.current.patchStatus).toBe('failed')
    })
  })
})
