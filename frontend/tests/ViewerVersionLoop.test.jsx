/**
 * 뷰어 수정 루프 결함 수정 테스트 (버그 신고 2026-07-06 대응).
 *
 *   Fix A — [최종본 다운로드] 버튼이 선택된 버전과 연결된다 (기존: dead button)
 *   Fix B — 채팅발 수정계획 수신(refreshKey 변경) 시 버전 목록을 재조회한다
 *   Feature C — patch_plan 말풍선에 변경 항목 체크박스 + 선택 반영
 *
 * Red → Green → Refactor
 */

import { render, screen, fireEvent, waitFor, renderHook, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('../src/components/Ic', () => ({
  Ic: ({ name }) => <span data-testid={`ic-${name}`} />,
}))

const mockFetchVersions = vi.hoisted(() => vi.fn())
vi.mock('../src/api/documentChanges', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, fetchDocumentVersions: mockFetchVersions }
})

import { ViewerToolbar } from '../src/pages/Workspace/ViewerToolbar'
import { useDocumentVersions } from '../src/hooks/useDocumentVersions'
import { MessageBubble } from '../src/components/MessageBubble'

beforeEach(() => {
  vi.clearAllMocks()
})

// ── Fix A: 다운로드 버튼 ────────────────────────────────────────────────────

describe('ViewerToolbar 다운로드', () => {
  it('onDownload가 있으면 [최종본 다운로드] 클릭 시 호출된다', () => {
    const onDownload = vi.fn()
    render(<ViewerToolbar onDownload={onDownload} />)

    fireEvent.click(screen.getByText(/최종본 다운로드/))
    expect(onDownload).toHaveBeenCalledTimes(1)
  })

  it('[회귀] onDownload 없이 artifactUrl만 있으면 기존 anchor 다운로드를 유지한다', () => {
    render(<ViewerToolbar artifactUrl="/media/artifacts/a.xlsx" />)
    const link = screen.getByText(/최종본 다운로드/).closest('a')
    expect(link).toBeTruthy()
    expect(link.getAttribute('href')).toBe('/media/artifacts/a.xlsx')
  })
})

// ── Fix B: 버전 목록 재조회 ─────────────────────────────────────────────────

describe('useDocumentVersions refreshKey', () => {
  it('refreshKey가 바뀌면 버전 목록을 재조회한다 (채팅발 draft 생성 감지)', async () => {
    mockFetchVersions.mockResolvedValue([{ id: 1, status: 'original', version_number: 1 }])

    const { rerender } = renderHook(
      ({ refreshKey }) => useDocumentVersions(10, null, refreshKey),
      { initialProps: { refreshKey: null } },
    )
    await waitFor(() => expect(mockFetchVersions).toHaveBeenCalledTimes(1))

    // 채팅에서 새 draft 버전(id=7)이 생겼다는 신호
    rerender({ refreshKey: 7 })
    await waitFor(() => expect(mockFetchVersions).toHaveBeenCalledTimes(2))
  })
})

// ── Feature C: patch_plan 말풍선 체크박스 ───────────────────────────────────

function makePatchPlanMessage(changes) {
  return {
    id: 100,
    role: 'assistant',
    content: '수정 계획이 생성되었습니다.',
    has_snippet: true,
    snippet_data: {
      type: 'patch_plan',
      version_id: 7,
      upload_id: 10,
      changes,
    },
  }
}

const TWO_CHANGES = [
  { id: 501, operation: 'replace_cell', title: '금액 수정', original: '1000', replacement: '2000' },
  { id: 502, operation: 'set_number_format', title: '날짜 형식 통일', original: '', replacement: '' },
]

describe('PatchPlanBubble 변경 항목 체크박스', () => {
  it('변경 항목 제목이 말풍선 안에 리스트로 표시된다', () => {
    render(<MessageBubble message={makePatchPlanMessage(TWO_CHANGES)} onAcceptPatch={vi.fn()} />)
    expect(screen.getByText(/금액 수정/)).toBeInTheDocument()
    expect(screen.getByText(/날짜 형식 통일/)).toBeInTheDocument()
  })

  it('체크박스는 기본 전체 선택 상태이고 버튼 라벨은 [전체 반영]이다', () => {
    render(<MessageBubble message={makePatchPlanMessage(TWO_CHANGES)} onAcceptPatch={vi.fn()} />)
    const boxes = screen.getAllByRole('checkbox')
    expect(boxes).toHaveLength(2)
    expect(boxes.every(b => b.checked)).toBe(true)
    expect(screen.getByText('전체 반영')).toBeInTheDocument()
  })

  it('하나를 해제하면 버튼 라벨이 [선택 반영 (1/2)]로 바뀐다', () => {
    render(<MessageBubble message={makePatchPlanMessage(TWO_CHANGES)} onAcceptPatch={vi.fn()} />)
    fireEvent.click(screen.getAllByRole('checkbox')[1])
    expect(screen.getByText(/선택 반영 \(1\/2\)/)).toBeInTheDocument()
  })

  it('부분 선택 후 반영 클릭 시 선택된 change id 배열로 onAcceptPatch를 호출한다', async () => {
    const onAcceptPatch = vi.fn().mockResolvedValue()
    render(<MessageBubble message={makePatchPlanMessage(TWO_CHANGES)} onAcceptPatch={onAcceptPatch} />)

    fireEvent.click(screen.getAllByRole('checkbox')[1]) // 502 해제
    fireEvent.click(screen.getByText(/선택 반영/))

    await waitFor(() => expect(onAcceptPatch).toHaveBeenCalledWith([501]))
  })

  it('전체 선택 상태로 반영하면 기존 계약대로 인자 없이 호출한다 (전체 반영)', async () => {
    const onAcceptPatch = vi.fn().mockResolvedValue()
    render(<MessageBubble message={makePatchPlanMessage(TWO_CHANGES)} onAcceptPatch={onAcceptPatch} />)

    fireEvent.click(screen.getByText('전체 반영'))
    await waitFor(() => expect(onAcceptPatch).toHaveBeenCalledWith())
  })

  it('[경계] 전부 해제하면 반영 버튼이 비활성화된다', () => {
    render(<MessageBubble message={makePatchPlanMessage(TWO_CHANGES)} onAcceptPatch={vi.fn()} />)
    screen.getAllByRole('checkbox').forEach(b => fireEvent.click(b))
    expect(screen.getByText(/선택 반영 \(0\/2\)/).closest('button')).toBeDisabled()
  })
})
