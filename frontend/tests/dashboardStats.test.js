/**
 * getDashboardStats API 함수 단위 테스트
 * Red → Green → Refactor TDD
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

// client.js는 모듈 최상단에서 axios.create()로 api 인스턴스를 만들고
// getDashboardStats가 그 인스턴스를 직접 참조하므로, client.js export를
// 모킹하는 대신 axios 자체를 모킹해 내부 api.get 호출을 가로챈다.
const mockGet = vi.hoisted(() => vi.fn())
vi.mock('axios', () => ({
  default: {
    create: () => ({
      get: mockGet,
      // client.js가 request(인증)·response(429 크레딧) 인터셉터를 모두 등록하므로 둘 다 필요
      interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
    }),
  },
}))

import { getDashboardStats } from '../src/api/client'

describe('getDashboardStats', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('/dashboard/stats/ 엔드포인트로 GET 요청을 보낸다', async () => {
    mockGet.mockResolvedValue({ data: { ai_calls: 0 } })

    await getDashboardStats()

    expect(mockGet).toHaveBeenCalledWith('/dashboard/stats/')
  })

  it('서버 응답 data를 그대로 반환한다', async () => {
    const serverResponse = {
      ai_calls: 42,
      processed_documents: 10,
      generated_revisions: 5,
      failed_jobs: 1,
      input_tokens: 1000,
      output_tokens: 500,
      total_tokens: 1500,
      estimated_cost: 12000,
      monthly_token_limit: 2000000,
      monthly_cost_limit: 500000,
      token_usage_percent: 1,
      cost_usage_percent: 2,
    }
    mockGet.mockResolvedValue({ data: serverResponse })

    const result = await getDashboardStats()

    expect(result).toEqual(serverResponse)
  })

  it('axios 오류를 상위로 전파한다', async () => {
    mockGet.mockRejectedValue(new Error('네트워크 오류'))

    await expect(getDashboardStats()).rejects.toThrow('네트워크 오류')
  })
})
