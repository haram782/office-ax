import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockUseDocumentVersions = vi.hoisted(() => vi.fn())
const mockUsePatchTrigger = vi.hoisted(() => vi.fn())
const mockUseChangeSuggestions = vi.hoisted(() => vi.fn())

vi.mock('../src/hooks/useDocumentVersions', () => ({
  useDocumentVersions: (...args) => mockUseDocumentVersions(...args),
}))

vi.mock('../src/hooks/usePatchTrigger', () => ({
  usePatchTrigger: (...args) => mockUsePatchTrigger(...args),
}))

vi.mock('../src/hooks/useChangeSuggestions', () => ({
  useChangeSuggestions: (...args) => mockUseChangeSuggestions(...args),
}))

vi.mock('../src/components/DocumentPanel', () => ({
  resolveViewer: (_previewData, options) => (
    <div data-testid="viewer-highlights">{options.highlights.length}</div>
  ),
}))

import { WorkspaceCenter } from '../src/pages/Workspace/WorkspaceCenter'

const VERSIONS = [
  { id: 1, version_number: 1, status: 'original', label: '원본', created_at: '2026-07-08T05:10:00' },
  { id: 2, version_number: 2, status: 'draft', label: '박하람 교체안', created_at: '2026-07-08T05:20:00' },
]

const READY_VERSIONS = [
  VERSIONS[0],
  {
    id: 2,
    version_number: 2,
    status: 'ready',
    label: '박하람 교체안',
    created_at: '2026-07-08T05:20:00',
    applied_change_ids: ['s1'],
  },
]

function renderCenter(props = {}) {
  return render(
    <WorkspaceCenter
      previewData={{
        id: 10,
        filename: 'test.hwp',
        fileUrl: '/media/test.hwp',
        artifactUrl: null,
        snippetData: {},
      }}
      onCloseViewer={vi.fn()}
      showBanner={false}
      onDismissBanner={vi.fn()}
      suggestedWorkflow={null}
      localPatchData={props.localPatchData ?? { version_id: 2, patch_changes: [] }}
      onAcceptAllReady={props.onAcceptAllReady ?? vi.fn()}
    />,
  )
}

describe('WorkspaceCenter 버전별 수정 카드', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseDocumentVersions.mockReturnValue({ versions: VERSIONS })
    mockUsePatchTrigger.mockReturnValue({ patchStatus: null, trigger: vi.fn() })
    mockUseChangeSuggestions.mockReturnValue({
      suggestions: [{ id: 's1', title: '박하람 텍스트 교체', status: 'pending' }],
      statuses: { s1: 'pending' },
      setStatuses: vi.fn(),
      selectedSuggestionId: null,
      setSelectedSuggestionId: vi.fn(),
      highlights: [{ id: 's1', status: 'pending' }],
      pendingIds: new Set(),
      isAcceptingAll: false,
      acceptAllError: null,
      autoRejectedIds: new Set(),
      handleSetStatus: vi.fn(),
      handleAcceptAll: vi.fn(),
      handleSelectHighlight: vi.fn(),
    })
  })

  it('원본 버전을 선택하면 현재 편집 버전의 수정 카드를 숨긴다', async () => {
    renderCenter()

    expect(await screen.findByText('박하람 텍스트 교체')).toBeInTheDocument()
    expect(screen.getByTestId('viewer-highlights')).toHaveTextContent('1')

    await userEvent.click(screen.getByRole('button', { name: /원본/ }))

    await waitFor(() => {
      expect(screen.queryByText('박하람 텍스트 교체')).not.toBeInTheDocument()
    })
    expect(screen.getByTestId('viewer-highlights')).toHaveTextContent('0')

    await userEvent.click(screen.getByRole('button', { name: /박하람 교체안/ }))

    expect(await screen.findByText('박하람 텍스트 교체')).toBeInTheDocument()
    expect(screen.getByTestId('viewer-highlights')).toHaveTextContent('1')
  })

  it('전체 반영 후 현재 버전이 draft이면 수정본 생성을 자동 트리거한다', async () => {
    const trigger = vi.fn().mockResolvedValue(undefined)
    const handleAcceptAll = vi.fn().mockResolvedValue(undefined)
    let registeredAcceptAll = null

    mockUsePatchTrigger.mockReturnValue({ patchStatus: null, trigger })
    mockUseChangeSuggestions.mockReturnValue({
      suggestions: [{ id: 's1', title: '박하람 텍스트 교체', status: 'pending' }],
      statuses: { s1: 'pending' },
      setStatuses: vi.fn(),
      selectedSuggestionId: null,
      setSelectedSuggestionId: vi.fn(),
      highlights: [{ id: 's1', status: 'pending' }],
      pendingIds: new Set(),
      isAcceptingAll: false,
      acceptAllError: null,
      autoRejectedIds: new Set(),
      handleSetStatus: vi.fn(),
      handleAcceptAll,
      handleSelectHighlight: vi.fn(),
    })

    renderCenter({
      onAcceptAllReady: (fn) => {
        registeredAcceptAll = fn
      },
    })

    await waitFor(() => {
      expect(registeredAcceptAll).toEqual(expect.any(Function))
    })

    await registeredAcceptAll()

    expect(handleAcceptAll).toHaveBeenCalledWith(null)
    expect(trigger).toHaveBeenCalledTimes(1)
  })

  it('현재 버전이 draft이고 제안이 이미 적용됨이면 수정본 생성을 자동 트리거한다', async () => {
    const trigger = vi.fn().mockResolvedValue(undefined)

    mockUsePatchTrigger.mockReturnValue({ patchStatus: null, trigger })
    mockUseChangeSuggestions.mockReturnValue({
      suggestions: [{ id: 's1', title: '박하람 텍스트 교체', status: 'applied' }],
      statuses: { s1: 'applied' },
      setStatuses: vi.fn(),
      selectedSuggestionId: null,
      setSelectedSuggestionId: vi.fn(),
      highlights: [{ id: 's1', status: 'applied' }],
      pendingIds: new Set(),
      isAcceptingAll: false,
      acceptAllError: null,
      autoRejectedIds: new Set(),
      handleSetStatus: vi.fn(),
      handleAcceptAll: vi.fn(),
      handleSelectHighlight: vi.fn(),
    })

    renderCenter({ localPatchData: { version_id: '2', patch_changes: [] } })

    await waitFor(() => {
      expect(trigger).toHaveBeenCalledTimes(1)
    })
  })

  it('수정본 생성 전 applied 상태는 반영됨이 아니라 생성 대기로 표시한다', async () => {
    mockUseChangeSuggestions.mockReturnValue({
      suggestions: [{ id: 's1', title: '박하람 텍스트 교체', status: 'applied' }],
      statuses: { s1: 'applied' },
      setStatuses: vi.fn(),
      selectedSuggestionId: null,
      setSelectedSuggestionId: vi.fn(),
      highlights: [{ id: 's1', status: 'applied' }],
      pendingIds: new Set(),
      isAcceptingAll: false,
      acceptAllError: null,
      autoRejectedIds: new Set(),
      handleSetStatus: vi.fn(),
      handleAcceptAll: vi.fn(),
      handleSelectHighlight: vi.fn(),
    })

    renderCenter()

    expect(await screen.findByText('생성 대기')).toBeInTheDocument()
    expect(screen.queryByText('반영됨')).not.toBeInTheDocument()
  })

  it('완료된 수정본은 적용 operation 기준으로 반영됨을 표시하고 되돌리기를 숨긴다', async () => {
    mockUseDocumentVersions.mockReturnValue({ versions: READY_VERSIONS })
    mockUseChangeSuggestions.mockReturnValue({
      suggestions: [{ id: 's1', title: '박하람 텍스트 교체', status: 'rejected' }],
      statuses: { s1: 'rejected' },
      setStatuses: vi.fn(),
      selectedSuggestionId: null,
      setSelectedSuggestionId: vi.fn(),
      highlights: [{ id: 's1', status: 'rejected' }],
      pendingIds: new Set(),
      isAcceptingAll: false,
      acceptAllError: null,
      autoRejectedIds: new Set(),
      handleSetStatus: vi.fn(),
      handleAcceptAll: vi.fn(),
      handleSelectHighlight: vi.fn(),
    })

    renderCenter()

    expect(await screen.findByText('반영됨')).toBeInTheDocument()
    expect(screen.queryByText('거절됨')).not.toBeInTheDocument()
    expect(screen.queryByText('되돌리기')).not.toBeInTheDocument()
  })
})
