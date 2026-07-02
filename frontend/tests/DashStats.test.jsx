/**
 * DashStats 대시보드 통계 카드 — 실제 백엔드 응답 필드 렌더링 테스트
 * Red → Green → Refactor TDD
 */

import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockGetDashboardStats = vi.hoisted(() => vi.fn())
vi.mock('../src/api/client', () => ({
  getDashboardStats: mockGetDashboardStats,
}))

import { DashStats } from '../src/pages/Dashboard/DashStats'

const BACKEND_RESPONSE = {
  month_start: '2026-07-01',
  ai_calls: 42,
  processed_documents: 10,
  generated_revisions: 5,
  failed_jobs: 2,
  input_tokens: 900000,
  output_tokens: 300000,
  total_tokens: 1200000,
  estimated_cost: 150000,
  monthly_token_limit: 2000000,
  monthly_cost_limit: 500000,
  token_usage_percent: 60,
  cost_usage_percent: 30,
}

describe('DashStats', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('백엔드 응답 필드(total_tokens, estimated_cost 등)를 그대로 렌더링한다', async () => {
    mockGetDashboardStats.mockResolvedValue(BACKEND_RESPONSE)

    render(<DashStats />)

    await waitFor(() => {
      expect(screen.getByText('1,200,000')).toBeTruthy()
    })
    expect(screen.getByText(/2,000,000/)).toBeTruthy()
    expect(screen.getByText(/150,000/)).toBeTruthy()
    expect(screen.getByText('42 건')).toBeTruthy()
    expect(screen.getByText(/문서 분석 10/)).toBeTruthy()
    expect(screen.getByText(/수정본 생성 5/)).toBeTruthy()
    expect(screen.getByText(/실패 2/)).toBeTruthy()
  })

  it('충전하기/예치금 등 결제성 문구를 노출하지 않는다', async () => {
    mockGetDashboardStats.mockResolvedValue(BACKEND_RESPONSE)

    render(<DashStats />)

    await waitFor(() => {
      expect(screen.getByText('1,200,000')).toBeTruthy()
    })
    expect(screen.queryByText('충전하기')).toBeNull()
    expect(screen.queryByText(/예치금/)).toBeNull()
  })

  it('이번 달 한도 / 예상 사용량 문구를 사용한다', async () => {
    mockGetDashboardStats.mockResolvedValue(BACKEND_RESPONSE)

    render(<DashStats />)

    await waitFor(() => {
      expect(screen.getAllByText(/이번 달 한도/).length).toBeGreaterThan(0)
    })
    expect(screen.getByText('이번 달 예상 사용량')).toBeTruthy()
  })
})
