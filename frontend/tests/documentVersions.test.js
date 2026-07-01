/**
 * fetchDocumentVersions / fetchVersionFileBlob API 함수 단위 테스트
 * Red → Green → Refactor TDD
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// vi.mock 팩토리 호이스팅 — mockGet을 api.get에 주입
const mockGet = vi.hoisted(() => vi.fn())
vi.mock('../src/api/client', () => ({
  api: { get: mockGet, patch: vi.fn(), post: vi.fn() },
}))

import { fetchDocumentVersions, fetchVersionFileBlob } from '../src/api/documentChanges'

describe('fetchDocumentVersions', () => {
  beforeEach(() => vi.clearAllMocks())

  it('올바른 엔드포인트로 GET 요청을 보낸다', async () => {
    mockGet.mockResolvedValue({ data: [] })

    await fetchDocumentVersions(10)

    expect(mockGet).toHaveBeenCalledWith('/uploads/10/versions/')
  })

  it('버전 배열을 반환한다', async () => {
    const versions = [{ id: 1, status: 'original', version_number: 1, label: '원본' }]
    mockGet.mockResolvedValue({ data: versions })

    const result = await fetchDocumentVersions(10)

    expect(result).toEqual(versions)
  })

  it('axios 오류를 상위로 전파한다', async () => {
    mockGet.mockRejectedValue(new Error('네트워크 오류'))

    await expect(fetchDocumentVersions(10)).rejects.toThrow('네트워크 오류')
  })
})

describe('fetchVersionFileBlob', () => {
  // URL.createObjectURL 모킹 — happy-dom에서 지원하지 않는 API
  const mockCreateObjectURL = vi.fn(() => 'blob:fake-url-123')
  const origCreateObjectURL = URL.createObjectURL

  beforeEach(() => {
    vi.clearAllMocks()
    URL.createObjectURL = mockCreateObjectURL
  })
  afterEach(() => {
    URL.createObjectURL = origCreateObjectURL
  })

  it('올바른 엔드포인트로 GET 요청을 보내고 responseType: blob을 사용한다', async () => {
    const fakeBlob = new Blob(['fake'], { type: 'application/xlsx' })
    mockGet.mockResolvedValue({ data: fakeBlob })

    await fetchVersionFileBlob(10, 2)

    expect(mockGet).toHaveBeenCalledWith(
      '/uploads/10/versions/2/file/',
      { responseType: 'blob' },
    )
  })

  it('Blob URL 문자열을 반환한다', async () => {
    const fakeBlob = new Blob(['fake'])
    mockGet.mockResolvedValue({ data: fakeBlob })

    const result = await fetchVersionFileBlob(10, 2)

    expect(result).toBe('blob:fake-url-123')
    expect(mockCreateObjectURL).toHaveBeenCalledWith(fakeBlob)
  })
})
