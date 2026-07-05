/**
 * 자동화 제안 배너 최소 연결 테스트 (점검 발견 A-3).
 *
 * 기존: 배너 트리거가 어디서도 발화되지 않아 영원히 표시되지 않고,
 *       백엔드 주간 패턴 감지(/workflows/)는 프론트에서 미호출.
 * 변경: useSuggestedWorkflow 훅이 제안을 조회하고, 닫으면 localStorage로 기억한다.
 *
 * Red → Green → Refactor
 */

import { renderHook, waitFor, act } from '@testing-library/react'
import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../src/components/Ic', () => ({
  Ic: ({ name }) => <span data-testid={`ic-${name}`} />,
}))

const mockGetSuggested = vi.hoisted(() => vi.fn())
vi.mock('../src/api/client', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, getSuggestedWorkflows: mockGetSuggested }
})

import { useSuggestedWorkflow } from '../src/hooks/useSuggestedWorkflow'
import { AutomationBanner } from '../src/pages/Workspace/AutomationBanner'

const SUGGESTION = { id: 5, is_suggested: true, is_active: false, file_structure_hash: 'abc' }

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
})

describe('useSuggestedWorkflow', () => {
  it('제안된 워크플로우가 있으면 반환한다', async () => {
    mockGetSuggested.mockResolvedValue([SUGGESTION])
    const { result } = renderHook(() => useSuggestedWorkflow())
    await waitFor(() => expect(result.current.workflow).toEqual(SUGGESTION))
  })

  it('dismiss하면 workflow가 사라지고 재마운트에도 다시 뜨지 않는다', async () => {
    mockGetSuggested.mockResolvedValue([SUGGESTION])
    const { result } = renderHook(() => useSuggestedWorkflow())
    await waitFor(() => expect(result.current.workflow).toEqual(SUGGESTION))

    act(() => result.current.dismiss())
    expect(result.current.workflow).toBeNull()

    // 재마운트 — localStorage 기억으로 같은 제안은 다시 표시하지 않는다
    const { result: again } = renderHook(() => useSuggestedWorkflow())
    await waitFor(() => expect(mockGetSuggested).toHaveBeenCalledTimes(2))
    expect(again.current.workflow).toBeNull()
  })

  it('[경계] 제안이 없으면 null, API 실패 시에도 null로 조용히 처리한다', async () => {
    mockGetSuggested.mockRejectedValue(new Error('down'))
    const { result } = renderHook(() => useSuggestedWorkflow())
    await waitFor(() => expect(mockGetSuggested).toHaveBeenCalled())
    expect(result.current.workflow).toBeNull()
  })

  it('이미 활성화된 워크플로우는 제안으로 띄우지 않는다', async () => {
    mockGetSuggested.mockResolvedValue([{ ...SUGGESTION, is_active: true }])
    const { result } = renderHook(() => useSuggestedWorkflow())
    await waitFor(() => expect(mockGetSuggested).toHaveBeenCalled())
    expect(result.current.workflow).toBeNull()
  })
})

describe('AutomationBanner 실데이터 문구', () => {
  it('감지 근거(주간 반복 업로드)를 하드코딩 문구 대신 표시한다', () => {
    render(
      <MemoryRouter>
        <AutomationBanner workflow={SUGGESTION} onDismiss={vi.fn()} />
      </MemoryRouter>
    )
    expect(screen.getByText(/매주 반복 업로드/)).toBeInTheDocument()
    expect(screen.queryByText(/동일한 보정 작업이 3회 반복/)).toBeNull()
  })
})
