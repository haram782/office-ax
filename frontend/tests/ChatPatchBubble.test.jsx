/**
 * ChatPatchBubble TDD 테스트
 * 채팅 기반 문서 수정 요청 — patch_plan 말풍선 + 액션 버튼 동작 검증
 *
 * Red → Green → Refactor
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Ic 아이콘은 테스트 목적상 span으로 대체
vi.mock('../src/components/Ic', () => ({
  Ic: ({ name }) => <span data-testid={`ic-${name}`} />,
}))

import { MessageBubble } from '../src/components/MessageBubble'

// ── 픽스처 ─────────────────────────────────────────────────────────────────────

const PATCH_PLAN_MSG = {
  id: 'msg-1',
  role: 'assistant',
  source_type: 'patch_plan',
  content: '아래 2개 항목을 수정합니다.',
  snippet_data: {
    patch_changes: [
      { id: 1, operation_id: 'op-1', title: '항목 1', anchor: { type: 'cell', cell: 'A1', sheet: 'Sheet1' } },
      { id: 2, operation_id: 'op-2', title: '항목 2', anchor: { type: 'cell', cell: 'B2', sheet: 'Sheet1' } },
    ],
    version_id: 99,
  },
  created_at: '2026-06-26T10:00:00Z',
}

// source_type 없는 기존 형식 — 리그레션 확인용
const LEGACY_CHAT_MSG = {
  id: 'msg-2',
  role: 'assistant',
  content: '안녕하세요, 무엇을 도와드릴까요?',
  created_at: '2026-06-26T10:00:00Z',
}

// source_type='chat' 명시 형식
const NORMAL_CHAT_MSG = {
  id: 'msg-3',
  role: 'assistant',
  source_type: 'chat',
  content: '일반 응답입니다.',
  created_at: '2026-06-26T10:00:00Z',
}

// has_snippet=true 기존 메시지 — SnippetCard 리그레션용
const SNIPPET_MSG = {
  id: 'msg-4',
  role: 'assistant',
  source_type: 'chat',
  content: '분석 결과입니다.',
  has_snippet: true,
  snippet_data: {
    type: 'excel_preview',
    headers: ['A', 'B'],
    preview_rows: [['1', '2']],
    corrections: [],
  },
  created_at: '2026-06-26T10:00:00Z',
}

// ── patch_plan 말풍선 ─────────────────────────────────────────────────────────

describe('MessageBubble — patch_plan 말풍선', () => {
  beforeEach(() => vi.clearAllMocks())

  it('[happy] source_type=patch_plan 이면 [전체 반영] 버튼이 렌더된다', () => {
    render(
      <MessageBubble
        message={PATCH_PLAN_MSG}
        onAcceptPatch={vi.fn()}
        onRejectPatch={vi.fn()}
      />
    )
    expect(screen.getByRole('button', { name: /전체 반영/ })).toBeTruthy()
  })

  it('[happy] source_type=patch_plan 이면 [보류] 버튼이 렌더된다', () => {
    render(
      <MessageBubble
        message={PATCH_PLAN_MSG}
        onAcceptPatch={vi.fn()}
        onRejectPatch={vi.fn()}
      />
    )
    expect(screen.getByRole('button', { name: /보류/ })).toBeTruthy()
  })

  it('[happy] patch_changes 개수가 수정 요약에 표시된다', () => {
    render(
      <MessageBubble
        message={PATCH_PLAN_MSG}
        onAcceptPatch={vi.fn()}
        onRejectPatch={vi.fn()}
      />
    )
    expect(screen.getByText(/2개 변경사항/)).toBeTruthy()
  })

  it('[happy] [전체 반영] 클릭 시 onAcceptPatch가 호출된다', async () => {
    const onAcceptPatch = vi.fn().mockResolvedValue(undefined)
    render(
      <MessageBubble
        message={PATCH_PLAN_MSG}
        onAcceptPatch={onAcceptPatch}
        onRejectPatch={vi.fn()}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /전체 반영/ }))
    await waitFor(() => expect(onAcceptPatch).toHaveBeenCalledTimes(1))
  })

  it('[happy] [보류] 클릭 시 onRejectPatch가 호출된다', () => {
    const onRejectPatch = vi.fn()
    render(
      <MessageBubble
        message={PATCH_PLAN_MSG}
        onAcceptPatch={vi.fn()}
        onRejectPatch={onRejectPatch}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /보류/ }))
    expect(onRejectPatch).toHaveBeenCalledTimes(1)
  })

  it('[happy] 메시지 content가 말풍선에 표시된다', () => {
    render(
      <MessageBubble
        message={PATCH_PLAN_MSG}
        onAcceptPatch={vi.fn()}
        onRejectPatch={vi.fn()}
      />
    )
    expect(screen.getByText(/2개 항목을 수정합니다/)).toBeTruthy()
  })

  it('[boundary] source_type=chat 이면 [전체 반영] 버튼이 없다', () => {
    render(<MessageBubble message={NORMAL_CHAT_MSG} />)
    expect(screen.queryByRole('button', { name: /전체 반영/ })).toBeNull()
  })

  it('[boundary] source_type 없는 기존 메시지에는 [전체 반영] 버튼이 없다', () => {
    render(<MessageBubble message={LEGACY_CHAT_MSG} />)
    expect(screen.queryByRole('button', { name: /전체 반영/ })).toBeNull()
  })

  it('[boundary] snippet_data.patch_changes가 없으면 변경사항 카운트 배지가 없다', () => {
    const noChangesMsg = { ...PATCH_PLAN_MSG, snippet_data: { version_id: 99 } }
    render(
      <MessageBubble
        message={noChangesMsg}
        onAcceptPatch={vi.fn()}
        onRejectPatch={vi.fn()}
      />
    )
    expect(screen.queryByText(/변경사항/)).toBeNull()
  })

  it('[failure] onAcceptPatch가 없어도 [전체 반영] 클릭 시 에러가 발생하지 않는다', () => {
    render(<MessageBubble message={PATCH_PLAN_MSG} onRejectPatch={vi.fn()} />)
    expect(() => fireEvent.click(screen.getByRole('button', { name: /전체 반영/ }))).not.toThrow()
  })

  it('[failure] onRejectPatch가 없어도 [보류] 클릭 시 에러가 발생하지 않는다', () => {
    render(<MessageBubble message={PATCH_PLAN_MSG} onAcceptPatch={vi.fn()} />)
    expect(() => fireEvent.click(screen.getByRole('button', { name: /보류/ }))).not.toThrow()
  })

  it('[regression] 기존 chat 메시지 콘텐츠가 정상 렌더된다', () => {
    render(<MessageBubble message={LEGACY_CHAT_MSG} />)
    expect(screen.getByText(/안녕하세요/)).toBeTruthy()
  })

  it('[regression] has_snippet=true인 기존 메시지에 SnippetCard가 렌더된다', () => {
    render(<MessageBubble message={SNIPPET_MSG} onFileView={vi.fn()} />)
    expect(screen.getByText(/수정 내용 미리보기/)).toBeTruthy()
  })
})
