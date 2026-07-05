/**
 * 이메일 인박스 실데이터 연결 테스트 (점검 발견 A-1).
 *
 * 기존: getEmailInbox()가 하드코딩 목업 6건을 반환 — 백엔드 /email-inbox/ 미연결.
 * 변경: 실제 API를 호출하고 InboundEmailSerializer 필드를 화면 형태로 매핑한다.
 *
 * Red → Green → Refactor
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockGet = vi.hoisted(() => vi.fn())
vi.mock('axios', () => ({
  default: {
    create: () => ({
      get: mockGet,
      interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
    }),
  },
}))

import { getEmailInbox } from '../src/api/client'

beforeEach(() => { vi.clearAllMocks() })

describe('getEmailInbox 실연결', () => {
  it('/email-inbox/ 엔드포인트를 호출한다 (목업 반환 금지)', async () => {
    mockGet.mockResolvedValue({ data: [] })
    await getEmailInbox()
    expect(mockGet).toHaveBeenCalledWith('/email-inbox/')
  })

  it('백엔드 필드를 화면 형태(from/subject/file/time/status)로 매핑한다', async () => {
    mockGet.mockResolvedValue({
      data: [{
        id: 3,
        sender: 'tax@corp.co.kr',
        subject: '8월 세금계산서',
        attachment_filename: 'invoice_08.pdf',
        received_at: '2026-07-06T02:10:00+09:00',
        status: 'done',
      }],
    })

    const rows = await getEmailInbox()

    expect(rows).toHaveLength(1)
    expect(rows[0].from).toBe('tax@corp.co.kr')
    expect(rows[0].subject).toBe('8월 세금계산서')
    expect(rows[0].file).toBe('invoice_08.pdf')
    expect(rows[0].status).toBe('완료')
    expect(rows[0].time).toBeTruthy()
  })

  it('[경계] 빈 목록이면 빈 배열을 반환한다', async () => {
    mockGet.mockResolvedValue({ data: [] })
    const rows = await getEmailInbox()
    expect(rows).toEqual([])
  })
})
