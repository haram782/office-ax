/**
 * useChat — 폴링 종료 조건 TDD 테스트
 * Red → Green → Refactor
 *
 * 변경 배경:
 *   uploadId 있는 요청은 BE가 중간 안내 메시지(snippet_data 없음)와
 *   최종 patch_plan 메시지(snippet_data.type 있음)를 별도로 생성한다.
 *   기존 폴링 종료 조건(assistant 수 >= target)으로는 중간 메시지에서 바로 멈추므로
 *   snippet_data.type이 존재하는 메시지 도착 시에만 종료하도록 변경한다.
 */

import { renderHook, act, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// ── API 목킹 ─────────────────────────────────────────────────────────────────

const mockGetChatMessages    = vi.hoisted(() => vi.fn())
const mockSendChatMessage    = vi.hoisted(() => vi.fn())
const mockGetChatSessions    = vi.hoisted(() => vi.fn())
const mockCreateChatSession  = vi.hoisted(() => vi.fn())

vi.mock('../src/api/client', () => ({
  getChatMessages:   (...args) => mockGetChatMessages(...args),
  sendChatMessage:   (...args) => mockSendChatMessage(...args),
  getChatSessions:   (...args) => mockGetChatSessions(...args),
  createChatSession: (...args) => mockCreateChatSession(...args),
}))

import { useChat } from '../src/hooks/useChat'

// ── 픽스처 ──────────────────────────────────────────────────────────────────

// snippet_data 없는 중간 안내 메시지 (BE가 먼저 생성)
const INTERMEDIATE_MSG = {
  id: 'a1',
  role: 'assistant',
  content: '수정 계획을 생성하고 있습니다...',
  snippet_data: null,
  created_at: new Date().toISOString(),
}

// patch_plan 최종 메시지
const PATCH_PLAN_MSG = {
  id: 'a2',
  role: 'assistant',
  content: '수정 계획이 준비되었습니다.',
  snippet_data: { type: 'patch_plan', patch_changes: [], version_id: 1 },
  created_at: new Date().toISOString(),
}

// QA 응답 메시지
const QA_MSG = {
  id: 'a3',
  role: 'assistant',
  content: '네, 도와드릴게요.',
  snippet_data: { type: 'qa' },
  created_at: new Date().toISOString(),
}

// ── 헬퍼 ────────────────────────────────────────────────────────────────────

/** 훅 마운트 후 세션 초기화(getChatSessions)가 완료될 때까지 대기 */
async function mountAndInit() {
  const hook = renderHook(() => useChat())
  // getChatSessions 프로미스 해소 + effect 처리
  await act(async () => { await vi.advanceTimersByTimeAsync(0) })
  return hook
}

/** sendMessage 호출 후 async 체인 전체 완료 대기
 *  createChatSession + baseline getChatMessages + sendChatMessage + afterSend getChatMessages
 *  sendMessage 자체가 async이므로 act 안에서 await한다.
 */
async function sendAndFlush(result, content = '요청', files = [], uploadId = null) {
  await act(async () => {
    await result.current.sendMessage(content, files, uploadId)
  })
}

// ── 공통 설정 ────────────────────────────────────────────────────────────────

function setupMocks() {
  vi.clearAllMocks()
  mockGetChatSessions.mockResolvedValue([])
  mockCreateChatSession.mockResolvedValue({
    id: 'sess1',
    title: '새 대화',
    created_at: new Date().toISOString(),
  })
  mockSendChatMessage.mockResolvedValue({ message_id: 1, session_id: 'sess1', status: 'queued' })
}

// ── 인터벌 폴링 테스트 (fake timers 필요) ────────────────────────────────────

describe('useChat — 폴링 종료 조건 (인터벌)', () => {
  beforeEach(() => {
    setupMocks()
    vi.useFakeTimers()
  })
  afterEach(() => vi.useRealTimers())

  it('[happy] snippet_data.type="patch_plan" 메시지 도착 시 폴링이 종료된다', async () => {
    mockGetChatMessages
      .mockResolvedValueOnce([])               // baseline
      .mockResolvedValueOnce([])               // afterSend (즉시 종료 조건 미충족)
      .mockResolvedValueOnce([PATCH_PLAN_MSG]) // poll tick 1 → 종료

    const { result } = await mountAndInit()
    await sendAndFlush(result, '수정해줘', [], 123)

    expect(result.current.isProcessing).toBe(true)

    // 2500ms 폴링 틱 → patch_plan 도착 → 종료
    await act(async () => { await vi.advanceTimersByTimeAsync(2500) })

    expect(result.current.isProcessing).toBe(false)
  })

  it('[happy] snippet_data.type="qa" 메시지 도착 시 폴링이 종료된다', async () => {
    mockGetChatMessages
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([QA_MSG])

    const { result } = await mountAndInit()
    await sendAndFlush(result, '질문', [], null)

    expect(result.current.isProcessing).toBe(true)

    await act(async () => { await vi.advanceTimersByTimeAsync(2500) })

    expect(result.current.isProcessing).toBe(false)
  })

  it('[boundary] snippet_data 없는 중간 메시지가 도착해도 폴링이 계속된다', async () => {
    mockGetChatMessages
      .mockResolvedValueOnce([])                              // baseline
      .mockResolvedValueOnce([])                              // afterSend
      .mockResolvedValueOnce([INTERMEDIATE_MSG])              // poll tick 1 → snippet_data 없음 → 계속
      .mockResolvedValueOnce([INTERMEDIATE_MSG, PATCH_PLAN_MSG]) // poll tick 2 → 종료

    const { result } = await mountAndInit()
    await sendAndFlush(result, '수정해줘', [], 123)

    expect(result.current.isProcessing).toBe(true)

    // 첫 번째 틱 — 중간 메시지만 있으므로 아직 processing
    await act(async () => { await vi.advanceTimersByTimeAsync(2500) })
    expect(result.current.isProcessing).toBe(true)

    // 두 번째 틱 — patch_plan 도착 → 종료
    await act(async () => { await vi.advanceTimersByTimeAsync(2500) })
    expect(result.current.isProcessing).toBe(false)
  })
})

// ── 즉시 응답 테스트 (fake timers 환경에서 수행) ─────────────────────────────

describe('useChat — 즉시 응답 (afterSend snippet_data.type 있음)', () => {
  beforeEach(() => {
    setupMocks()
    vi.useFakeTimers()
  })
  afterEach(() => vi.useRealTimers())

  it('[regression] afterSend에 snippet_data.type 있으면 인터벌 없이 종료된다', async () => {
    mockGetChatMessages
      .mockResolvedValueOnce([])       // baseline
      .mockResolvedValueOnce([QA_MSG]) // afterSend → 즉시 종료

    const { result } = await mountAndInit()
    await sendAndFlush(result, '질문', [], null)

    // sendMessage 완료 직후 — 폴링 시작 없이 종료됐으면 2번만 호출
    expect(mockGetChatMessages).toHaveBeenCalledTimes(2)
  })
})
