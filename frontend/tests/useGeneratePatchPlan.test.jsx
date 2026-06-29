/**
 * useGeneratePatchPlan 훅 단위 테스트
 * Red → Green → Refactor TDD
 */

import { renderHook, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

// generatePatchPlan 모킹 — vi.hoisted로 호이스팅 이슈 방지
const mockGeneratePatchPlan = vi.hoisted(() => vi.fn())
vi.mock('../src/api/documentChanges', () => ({
  patchDocumentChange:  vi.fn(),
  triggerPatch:         vi.fn(),
  generatePatchPlan:    (...args) => mockGeneratePatchPlan(...args),
}))

import { useGeneratePatchPlan } from '../src/hooks/useGeneratePatchPlan'

describe('useGeneratePatchPlan', () => {
  beforeEach(() => vi.clearAllMocks())

  it('성공 시 onSuccess가 응답 데이터로 호출된다', async () => {
    const responseData = { version_id: 5, changes: [{ id: 1, operation_id: 'op-1' }] }
    mockGeneratePatchPlan.mockResolvedValue(responseData)
    const onSuccess = vi.fn()

    const { result } = renderHook(() => useGeneratePatchPlan(10, onSuccess))

    await act(async () => { await result.current.generate('프롬프트') })

    expect(onSuccess).toHaveBeenCalledWith(responseData)
  })

  it('실패 시 error 상태가 설정된다', async () => {
    mockGeneratePatchPlan.mockRejectedValue(new Error('생성 실패'))
    const onSuccess = vi.fn()

    const { result } = renderHook(() => useGeneratePatchPlan(10, onSuccess))

    await act(async () => { await result.current.generate('프롬프트') })

    expect(result.current.error).toBeTruthy()
    expect(onSuccess).not.toHaveBeenCalled()
  })

  it('generate 호출 중 isGenerating이 true이고 완료 후 false가 된다', async () => {
    let resolveFn
    mockGeneratePatchPlan.mockReturnValue(new Promise(resolve => { resolveFn = resolve }))
    const onSuccess = vi.fn()

    const { result } = renderHook(() => useGeneratePatchPlan(10, onSuccess))

    act(() => { result.current.generate('프롬프트') })

    // 완료 전 → isGenerating true
    expect(result.current.isGenerating).toBe(true)

    // 완료 후 → isGenerating false
    await act(async () => { resolveFn({ version_id: 5, changes: [] }) })
    expect(result.current.isGenerating).toBe(false)
  })

  it('초기 상태는 isGenerating=false, error=null이다', () => {
    const { result } = renderHook(() => useGeneratePatchPlan(10, vi.fn()))

    expect(result.current.isGenerating).toBe(false)
    expect(result.current.error).toBeNull()
  })
})
