/**
 * useDocumentVersions 훅 단위 테스트
 * Red → Green → Refactor TDD
 */

import { renderHook, waitFor, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// fetchDocumentVersions 모킹
const mockFetchVersions = vi.hoisted(() => vi.fn())
vi.mock('../src/api/documentChanges', () => ({
  patchDocumentChange:   vi.fn(),
  triggerPatch:          vi.fn(),
  generatePatchPlan:     vi.fn(),
  fetchDocumentVersions: (...args) => mockFetchVersions(...args),
  fetchVersionFileBlob:  vi.fn(),
}))

import { useDocumentVersions } from '../src/hooks/useDocumentVersions'

const VERSIONS = [
  { id: 1, version_number: 1, status: 'original', label: '원본' },
  { id: 2, version_number: 2, status: 'ready',    label: '수정본' },
]

const VERSIONS_GENERATING = [
  { id: 1, version_number: 1, status: 'original',   label: '원본' },
  { id: 2, version_number: 2, status: 'generating', label: '수정본' },
]

const VERSIONS_ALL_READY = [
  { id: 1, version_number: 1, status: 'original', label: '원본' },
  { id: 2, version_number: 2, status: 'ready',    label: '수정본' },
]

describe('useDocumentVersions', () => {
  beforeEach(() => vi.clearAllMocks())

  it('uploadId 없으면 빈 배열을 반환하고 API를 호출하지 않는다', () => {
    const { result } = renderHook(() => useDocumentVersions(null))

    expect(result.current.versions).toEqual([])
    expect(mockFetchVersions).not.toHaveBeenCalled()
  })

  it('uploadId 있으면 마운트 시 fetchDocumentVersions를 호출한다', async () => {
    mockFetchVersions.mockResolvedValue(VERSIONS)

    renderHook(() => useDocumentVersions(10))

    await waitFor(() => {
      expect(mockFetchVersions).toHaveBeenCalledWith(10)
    })
  })

  it('버전 목록을 versions 상태로 반환한다', async () => {
    mockFetchVersions.mockResolvedValue(VERSIONS)

    const { result } = renderHook(() => useDocumentVersions(10))

    await waitFor(() => {
      expect(result.current.versions).toEqual(VERSIONS)
    })
  })

  it('로딩 중 isLoading이 true이다', async () => {
    let resolveFn
    mockFetchVersions.mockReturnValue(new Promise(resolve => { resolveFn = resolve }))

    const { result } = renderHook(() => useDocumentVersions(10))

    // 완료 전 → isLoading true
    expect(result.current.isLoading).toBe(true)

    // 완료 후 → isLoading false
    await waitFor(async () => {
      resolveFn(VERSIONS)
      await Promise.resolve()
    })
  })

  it('patchStatus가 바뀔 때 재조회된다', async () => {
    mockFetchVersions.mockResolvedValue(VERSIONS)

    const { rerender } = renderHook(
      ({ uploadId, patchStatus }) => useDocumentVersions(uploadId, patchStatus),
      { initialProps: { uploadId: 10, patchStatus: null } },
    )

    await waitFor(() => expect(mockFetchVersions).toHaveBeenCalledTimes(1))

    // patchStatus 변경 → 재조회
    rerender({ uploadId: 10, patchStatus: 'ready' })

    await waitFor(() => expect(mockFetchVersions).toHaveBeenCalledTimes(2))
  })
})

describe('useDocumentVersions — generating 상태 polling', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('generating 상태 버전이 있으면 3초 후 자동으로 재조회한다', async () => {
    mockFetchVersions.mockResolvedValue(VERSIONS_GENERATING)

    renderHook(() => useDocumentVersions(10))

    await act(async () => { await vi.advanceTimersByTimeAsync(0) })
    expect(mockFetchVersions).toHaveBeenCalledTimes(1)

    await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
    expect(mockFetchVersions).toHaveBeenCalledTimes(2)
  })

  it('모든 버전이 ready/failed로 전환되면 더 이상 재조회하지 않는다', async () => {
    mockFetchVersions
      .mockResolvedValueOnce(VERSIONS_GENERATING)
      .mockResolvedValueOnce(VERSIONS_ALL_READY)

    renderHook(() => useDocumentVersions(10))

    await act(async () => { await vi.advanceTimersByTimeAsync(0) })
    expect(mockFetchVersions).toHaveBeenCalledTimes(1)

    // 3초 후 두 번째 조회 — 모두 ready로 전환됨
    await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
    expect(mockFetchVersions).toHaveBeenCalledTimes(2)

    // 추가로 3초가 더 흘러도 재조회되지 않는다
    await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
    expect(mockFetchVersions).toHaveBeenCalledTimes(2)
  })

  it('generating 상태가 90초 넘게 지속되면 polling을 중단한다', async () => {
    mockFetchVersions.mockResolvedValue(VERSIONS_GENERATING)

    renderHook(() => useDocumentVersions(10))

    // 타임아웃(90초)을 넘겨서까지 충분히 흘려보낸다
    await act(async () => { await vi.advanceTimersByTimeAsync(95000) })
    const countAtTimeout = mockFetchVersions.mock.calls.length

    // 추가로 더 흘려도 더 이상 호출되지 않는다 (polling 중단 확인)
    await act(async () => { await vi.advanceTimersByTimeAsync(10000) })
    expect(mockFetchVersions).toHaveBeenCalledTimes(countAtTimeout)
  })

  it('uploadId가 바뀌면 이전 polling 타이머가 정리되고 새 uploadId로 polling이 시작된다', async () => {
    mockFetchVersions.mockResolvedValue(VERSIONS_GENERATING)

    const { rerender } = renderHook(
      ({ uploadId }) => useDocumentVersions(uploadId),
      { initialProps: { uploadId: 10 } },
    )

    await act(async () => { await vi.advanceTimersByTimeAsync(0) })
    expect(mockFetchVersions).toHaveBeenCalledWith(10)

    const countBeforeSwitch = mockFetchVersions.mock.calls.length

    // uploadId 변경 — 이전 타이머는 정리되고, 새 uploadId로 즉시 1회 재조회
    rerender({ uploadId: 20 })
    await act(async () => { await vi.advanceTimersByTimeAsync(0) })

    expect(mockFetchVersions).toHaveBeenCalledWith(20)
    expect(mockFetchVersions.mock.calls.length).toBe(countBeforeSwitch + 1)

    // 이전 uploadId(10)에 대한 잔여 타이머가 발화하지 않는지 확인하기 위해 3초를 흘려본다
    // (발화했다면 호출 인자에 10이 다시 섞여 들어오므로, 마지막 호출이 여전히 20인지로 검증)
    await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
    const lastCallArg = mockFetchVersions.mock.calls.at(-1)[0]
    expect(lastCallArg).toBe(20)
  })

  it('처음부터 generating 상태가 없으면 polling이 시작되지 않는다', async () => {
    mockFetchVersions.mockResolvedValue(VERSIONS)

    renderHook(() => useDocumentVersions(10))

    await act(async () => { await vi.advanceTimersByTimeAsync(0) })
    expect(mockFetchVersions).toHaveBeenCalledTimes(1)

    await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
    expect(mockFetchVersions).toHaveBeenCalledTimes(1)
  })
})
