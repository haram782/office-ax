/**
 * generatePatchPlan API 함수 단위 테스트
 * Red → Green → Refactor TDD
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

// vi.mock 팩토리는 파일 상단으로 호이스팅되므로 vi.hoisted()로 먼저 선언
const mockPost = vi.hoisted(() => vi.fn())
vi.mock('../src/api/client', () => ({
  api: { post: mockPost, patch: vi.fn() },
}))

import { generatePatchPlan } from '../src/api/documentChanges'

describe('generatePatchPlan', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('올바른 엔드포인트로 POST 요청을 보낸다', async () => {
    mockPost.mockResolvedValue({ data: { version_id: 5, changes: [] } })

    await generatePatchPlan(10, '표 헤더를 굵게 바꿔주세요')

    expect(mockPost).toHaveBeenCalledWith(
      '/documents/uploads/10/generate-patch-plan/',
      { prompt: '표 헤더를 굵게 바꿔주세요' },
    )
  })

  it('서버 응답 data를 반환한다', async () => {
    const serverResponse = { version_id: 5, changes: [{ id: 1, operation_id: 'op-1' }] }
    mockPost.mockResolvedValue({ data: serverResponse })

    const result = await generatePatchPlan(10, '프롬프트')

    expect(result).toEqual(serverResponse)
  })

  it('axios 오류를 상위로 전파한다', async () => {
    mockPost.mockRejectedValue(new Error('서버 오류'))

    await expect(generatePatchPlan(10, '프롬프트')).rejects.toThrow('서버 오류')
  })
})
