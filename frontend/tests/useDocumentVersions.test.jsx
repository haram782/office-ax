/**
 * useDocumentVersions 훅 단위 테스트
 * Red → Green → Refactor TDD
 */

import { renderHook, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

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
