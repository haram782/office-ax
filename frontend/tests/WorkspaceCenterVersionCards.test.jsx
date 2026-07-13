import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockUseDocumentVersions = vi.hoisted(() => vi.fn())
const mockUsePatchTrigger = vi.hoisted(() => vi.fn())
const mockUseChangeSuggestions = vi.hoisted(() => vi.fn())
const mockFetchDocumentChanges = vi.hoisted(() => vi.fn())

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

vi.mock('../src/api/documentChanges', () => ({
  fetchDocumentChanges: (...args) => mockFetchDocumentChanges(...args),
  fetchVersionFileBlob: vi.fn(),
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

const READY_VERSIONS_NEEDS_CONFIRMATION = [
  VERSIONS[0],
  {
    id: 2,
    version_number: 2,
    status: 'ready',
    label: '박하람 교체안',
    created_at: '2026-07-08T05:20:00',
    applied_change_ids: [],
    needs_confirmation_change_ids: ['s1'],
  },
]

// 버전 전체가 후보 모호로 끝난 경우 — applied_change_ids가 비어 있고 version.status
// 자체가 'needs_confirmation'이다(READY_VERSIONS_NEEDS_CONFIRMATION은 부분 성공으로
// status='ready'인 경우라 서로 다른 코드 경로를 검증한다).
const NEEDS_CONFIRMATION_ONLY_VERSIONS = [
  VERSIONS[0],
  {
    id: 2,
    version_number: 2,
    status: 'needs_confirmation',
    label: '박하람 교체안',
    created_at: '2026-07-08T05:20:00',
    applied_change_ids: [],
    needs_confirmation_change_ids: ['s1'],
  },
]

function centerElement(props = {}) {
  return (
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
    />
  )
}

function renderCenter(props = {}) {
  return render(centerElement(props))
}

describe('WorkspaceCenter 버전별 수정 카드', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockFetchDocumentChanges.mockResolvedValue([])
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

  it('terminal 상태에 도달하면 version 필터로 최신 change를 다시 조회한다', async () => {
    mockUseDocumentVersions.mockReturnValue({ versions: [{
      ...VERSIONS[1],
      status: 'failed',
      failure_code: 'patch_failed',
      failure_message: '수정본을 만들지 못했습니다.',
    }] })
    mockFetchDocumentChanges.mockResolvedValue([{
      id: 99,
      operation_id: 's1',
      status: 'failed',
      failure_code: 'render_validation_failed',
      failure_message: '잘못된 결과물이 저장되지 않도록 생성을 중단했습니다.',
    }])

    renderCenter()

    await waitFor(() => {
      expect(mockFetchDocumentChanges).toHaveBeenCalledWith(10, 2)
    })
    await waitFor(() => {
      expect(mockUseChangeSuggestions.mock.calls.at(-1)[0].patch_changes[0]).toMatchObject({
        id: 99,
        failure_code: 'render_validation_failed',
      })
    })
  })

  it('change-level 안내가 없으면 version-level 안내를 표시한다', async () => {
    mockUseDocumentVersions.mockReturnValue({ versions: [{
      ...VERSIONS[1],
      status: 'failed',
      failure_code: 'source_file_missing',
      failure_message: '원본 파일을 찾지 못했습니다. 파일을 다시 업로드해 주세요.',
    }] })

    renderCenter()

    expect(await screen.findByRole('alert')).toHaveTextContent('원본 파일을 찾지 못했습니다')
  })

  it('이전 version의 늦은 refresh 응답을 현재 suggestion에 적용하지 않는다', async () => {
    let resolveOldRequest
    const oldRequest = new Promise(resolve => { resolveOldRequest = resolve })
    mockFetchDocumentChanges.mockImplementation((_uploadId, requestedVersionId) => {
      if (String(requestedVersionId) === '2') return oldRequest
      return Promise.resolve([{
        id: 103,
        operation_id: 'new-version-change',
        status: 'failed',
        failure_message: '새 버전 안내',
      }])
    })
    mockUseDocumentVersions.mockImplementation((_uploadId, _status, refreshKey) => ({
      versions: [{
        id: Number(refreshKey),
        version_number: Number(refreshKey),
        status: 'failed',
        label: `버전 ${refreshKey}`,
        failure_message: '버전 안내',
      }],
    }))

    const view = renderCenter({ localPatchData: { version_id: 2, patch_changes: [] } })
    await waitFor(() => expect(mockFetchDocumentChanges).toHaveBeenCalledWith(10, 2))

    view.rerender(centerElement({ localPatchData: { version_id: 3, patch_changes: [] } }))
    await waitFor(() => expect(mockFetchDocumentChanges).toHaveBeenCalledWith(10, 3))
    resolveOldRequest([{
      id: 102,
      operation_id: 'stale-version-change',
      status: 'failed',
      failure_message: '이전 버전 안내',
    }])

    await waitFor(() => {
      expect(mockUseChangeSuggestions.mock.calls.at(-1)[0]).toMatchObject({
        version_id: 3,
        patch_changes: [expect.objectContaining({ operation_id: 'new-version-change' })],
      })
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

  it('[버그 수정] AnchorResolver가 후보를 여러 개 찾아 멈춘 항목은 실패가 아니라 위치 확인 필요로 표시한다', async () => {
    mockUseDocumentVersions.mockReturnValue({ versions: READY_VERSIONS_NEEDS_CONFIRMATION })
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

    renderCenter()

    expect(await screen.findByText('위치 확인 필요')).toBeInTheDocument()
    expect(screen.queryByText('생성 실패')).not.toBeInTheDocument()
  })

  it('[코드리뷰 지적 수정] 버전 전체가 needs_confirmation으로 끝나도(ready가 아니어도) 위치 확인 필요로 표시하고 편집을 막는다', async () => {
    mockUseDocumentVersions.mockReturnValue({ versions: NEEDS_CONFIRMATION_ONLY_VERSIONS })
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

    renderCenter()

    // editingVersion.status === 'ready'만 검사하던 옛 코드라면 이 카드는 이 분기를
    // 타지 않고 아래 'applied' 분기로 빠져 '생성 대기'처럼 보였을 것이다.
    expect((await screen.findAllByText('위치 확인 필요')).length).toBeGreaterThanOrEqual(2)
    expect(screen.queryByText('생성 대기')).not.toBeInTheDocument()
    expect(screen.queryByText('반영됨')).not.toBeInTheDocument()

    // needs_confirmation은 종결 상태이므로 적용/거절 버튼이 다시 노출되면 안 된다
    // (canEditSuggestionStatuses가 이 상태를 인식하지 못하면 버튼이 다시 활성화된다).
    expect(screen.queryByTitle('적용')).not.toBeInTheDocument()
  })
})
