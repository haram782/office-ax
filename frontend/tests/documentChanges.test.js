/**
 * patchDocumentChange API 함수 단위 테스트
 * Red → Green → Refactor TDD
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

// vi.mock 팩토리는 파일 상단으로 호이스팅되므로 vi.hoisted()로 먼저 선언
const mockPatch = vi.hoisted(() => vi.fn())
const mockGet = vi.hoisted(() => vi.fn())
vi.mock('../src/api/client', () => ({
  api: { get: mockGet, patch: mockPatch },
}))

import { fetchDocumentChanges, patchDocumentChange } from '../src/api/documentChanges'

describe('patchDocumentChange', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('올바른 엔드포인트로 PATCH 요청을 보낸다', async () => {
    mockPatch.mockResolvedValue({ data: { id: 42, status: 'applied' } })

    await patchDocumentChange(42, 'applied')

    expect(mockPatch).toHaveBeenCalledWith(
      '/changes/42/',
      { status: 'applied' },
    )
  })

  it('rejected 상태도 올바른 body로 전송한다', async () => {
    mockPatch.mockResolvedValue({ data: { id: 7, status: 'rejected' } })

    await patchDocumentChange(7, 'rejected')

    expect(mockPatch).toHaveBeenCalledWith(
      '/changes/7/',
      { status: 'rejected' },
    )
  })

  it('서버 응답 data를 반환한다', async () => {
    const serverResponse = { id: 42, status: 'applied', created_at: '2026-01-01' }
    mockPatch.mockResolvedValue({ data: serverResponse })

    const result = await patchDocumentChange(42, 'applied')

    expect(result).toEqual(serverResponse)
  })

  it('axios 오류를 상위로 전파한다', async () => {
    mockPatch.mockRejectedValue(new Error('네트워크 오류'))

    await expect(patchDocumentChange(42, 'applied')).rejects.toThrow('네트워크 오류')
  })
})

describe('fetchDocumentChanges', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('version_id 필터로 최신 변경 목록을 조회한다', async () => {
    const changes = [{ id: 7, failure_code: 'patch_failed' }]
    mockGet.mockResolvedValue({ data: changes })

    const result = await fetchDocumentChanges(10, 22)

    expect(mockGet).toHaveBeenCalledWith(
      '/uploads/10/changes/',
      { params: { version_id: 22 } },
    )
    expect(result).toEqual(changes)
  })
})
