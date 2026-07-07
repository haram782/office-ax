/**
 * 대시보드 StyleView(RAG 문서 관리) 배선 테스트.
 *
 * 버그 신고: "대시보드에서 RAG문서 추가 버튼을 눌러도 아무런 반응이 없음"
 *
 * 조사 결과 3개 버튼이 배선되지 않았고(어투/양식 추가, 참조 파일 추가,
 * 상단 드롭존), 삭제 버튼도 onClick이 없었으며, getRagAssets 응답 모양
 * 변경(id/active 필드 제거)으로 "워크스페이스 적용중" 배지가 항상 꺼져
 * 있는 회귀도 발견했다. 어투/서식 전용 드롭존 2개로 분리한다(사용자 결정).
 *
 * Red → Green → Refactor
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('../src/components/Ic', () => ({
  Ic: ({ name }) => <span data-testid={`ic-${name}`} />,
}))

vi.mock('../src/components/DocumentPanel', () => ({
  resolveViewer: () => <div>뷰어</div>,
}))

const mockGetRagAssets = vi.hoisted(() => vi.fn())
const mockUploadRagAsset = vi.hoisted(() => vi.fn())
const mockDeleteRagAsset = vi.hoisted(() => vi.fn())
const mockGetRagAssetFileUrl = vi.hoisted(() => vi.fn())
vi.mock('../src/api/client', () => ({
  getRagAssets: mockGetRagAssets,
  uploadRagAsset: mockUploadRagAsset,
  deleteRagAsset: mockDeleteRagAsset,
  getRagAssetFileUrl: mockGetRagAssetFileUrl,
}))

import { StyleView } from '../src/pages/Dashboard/StyleView'

const TONE_GROUP = {
  name: '보고서_어투',
  assetIds: [11, 12],
  files: [
    { id: 11, name: 'a.docx', meta: '10 KB' },
    { id: 12, name: 'b.docx', meta: '20 KB' },
  ],
}
const FORM_GROUP = { name: '계약서_양식', assetIds: [21], files: [{ id: 21, name: 'c.hwp', meta: '5 KB' }] }

function mockAssets() {
  mockGetRagAssets.mockResolvedValue({ tones: [TONE_GROUP], forms: [FORM_GROUP] })
}

beforeEach(() => {
  vi.clearAllMocks()
  window.confirm = vi.fn(() => true)
})

describe('StyleView 초기 로딩', () => {
  it('실제 그룹 데이터를 렌더한다', async () => {
    mockAssets()
    render(<StyleView />)
    await waitFor(() => expect(screen.getByText('보고서_어투')).toBeInTheDocument())
    expect(screen.getByText('계약서_양식')).toBeInTheDocument()
  })
})

describe('레이아웃: 어투/서식 사이드바이사이드 열', () => {
  it('두 섹션 컨테이너가 같은 부모 아래 2열 그리드로 배치된다', async () => {
    mockAssets()
    render(<StyleView />)
    await waitFor(() => screen.getByText('보고서_어투'))

    const toneSection = screen.getByText('어투 스타일').closest('section')
    const formSection = screen.getByText('서식 양식').closest('section')
    expect(toneSection.parentElement).toBe(formSection.parentElement)
    expect(toneSection.parentElement.className).toMatch(/grid-cols-2/)
  })

  it('각 섹션 내부는 드롭존 다음 그룹이 세로로 쌓이는 단일 열이다 (2열 그리드 아님)', async () => {
    mockAssets()
    render(<StyleView />)
    await waitFor(() => screen.getByText('보고서_어투'))

    const toneSection = screen.getByText('어투 스타일').closest('section')
    expect(toneSection.className).not.toMatch(/grid-cols-2/)

    // 드롭존 → 그룹1 → 그룹2 순서로 세로 배치되는지 DOM 순서로 확인
    const dropzone = screen.getByTestId('tone-dropzone')
    const group1 = screen.getByText('보고서_어투').closest('div.rounded-2xl')
    expect(dropzone.compareDocumentPosition(group1) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })
})

describe('어투/서식 전용 드롭존', () => {
  it('어투 드롭존에 파일을 놓으면 kind=tone으로 업로드된다', async () => {
    mockAssets()
    mockUploadRagAsset.mockResolvedValue({ id: 99 })
    render(<StyleView />)
    await waitFor(() => screen.getByText('보고서_어투'))

    const file = new File(['x'], '새_어투.docx')
    fireEvent.drop(screen.getByTestId('tone-dropzone'), { dataTransfer: { files: [file] } })

    await waitFor(() => {
      expect(mockUploadRagAsset).toHaveBeenCalledWith('tone', '새_어투', file)
    })
  })

  it('서식 드롭존에 파일을 놓으면 kind=form으로 업로드된다', async () => {
    mockAssets()
    mockUploadRagAsset.mockResolvedValue({ id: 99 })
    render(<StyleView />)
    await waitFor(() => screen.getByText('계약서_양식'))

    const file = new File(['x'], '새_서식.hwp')
    fireEvent.drop(screen.getByTestId('form-dropzone'), { dataTransfer: { files: [file] } })

    await waitFor(() => {
      expect(mockUploadRagAsset).toHaveBeenCalledWith('form', '새_서식', file)
    })
  })

  it('업로드 성공 후 목록을 다시 조회한다', async () => {
    mockAssets()
    mockUploadRagAsset.mockResolvedValue({ id: 99 })
    render(<StyleView />)
    await waitFor(() => screen.getByText('보고서_어투'))

    fireEvent.drop(screen.getByTestId('tone-dropzone'), {
      dataTransfer: { files: [new File(['x'], '새_어투.docx')] },
    })

    await waitFor(() => expect(mockGetRagAssets).toHaveBeenCalledTimes(2))
  })
})

describe('참조 파일 추가 버튼', () => {
  it('클릭하면 파일 입력이 열리고, 선택 시 같은 그룹으로 업로드된다', async () => {
    mockAssets()
    mockUploadRagAsset.mockResolvedValue({ id: 100 })
    render(<StyleView />)
    await waitFor(() => screen.getByText('보고서_어투'))

    const addFileBtn = screen.getAllByText('참조 파일 추가')[0]
    fireEvent.click(addFileBtn)

    // 클릭 직후 나타나는 hidden input을 찾아 change 이벤트 발생
    const input = document.querySelector('input[type="file"][data-group="보고서_어투"]')
    const file = new File(['x'], '추가자료.docx')
    fireEvent.change(input, { target: { files: [file] } })

    await waitFor(() => {
      expect(mockUploadRagAsset).toHaveBeenCalledWith('tone', '보고서_어투', file)
    })
  })
})

describe('파일 삭제', () => {
  it('삭제 버튼 클릭 시 확인 후 deleteRagAsset을 호출하고 목록을 새로고침한다', async () => {
    mockAssets()
    mockDeleteRagAsset.mockResolvedValue()
    render(<StyleView />)
    await waitFor(() => screen.getByText('a.docx'))

    const row = screen.getByText('a.docx').closest('div[class*="flex items-center"]')
    fireEvent.click(row.querySelector('button:last-child'))

    await waitFor(() => expect(mockDeleteRagAsset).toHaveBeenCalledWith(11))
    expect(mockGetRagAssets).toHaveBeenCalledTimes(2)
  })

  it('[안전] 확인 취소 시 삭제하지 않는다', async () => {
    window.confirm = vi.fn(() => false)
    mockAssets()
    render(<StyleView />)
    await waitFor(() => screen.getByText('a.docx'))

    const row = screen.getByText('a.docx').closest('div[class*="flex items-center"]')
    fireEvent.click(row.querySelector('button:last-child'))

    expect(mockDeleteRagAsset).not.toHaveBeenCalled()
  })
})

describe('파일 보기', () => {
  it('파일명 클릭 시 fileUrl을 조회해 팝업을 연다', async () => {
    mockAssets()
    mockGetRagAssetFileUrl.mockResolvedValue('/media/rag_assets/1/a.docx')
    render(<StyleView />)
    await waitFor(() => screen.getByText('a.docx'))

    fireEvent.click(screen.getByText('a.docx'))

    await waitFor(() => expect(mockGetRagAssetFileUrl).toHaveBeenCalledWith(11))
    expect(await screen.findByText(/RAG 문서 · a.docx/)).toBeInTheDocument()
  })
})

describe('드롭존 안정성 (리뷰 반영)', () => {
  // happy-dom은 fireEvent.dragLeave(el, {relatedTarget})의 relatedTarget을 무시하므로
  // (eventInit으로 전달돼도 실제 이벤트 객체에 반영되지 않음), Object.defineProperty로
  // 직접 주입한 네이티브 Event를 dispatch하는 표준 우회법을 쓴다.
  // [복구 메모] 이 헬퍼와 아래 두 테스트는 PR #11 커밋 시 git add 누락으로 유실됐다가
  // 여기서 복구되었다 — StyleView.jsx의 프로덕션 수정 자체는 정상 병합되어 있었다.
  function dragLeaveWithRelatedTarget(el, relatedTarget) {
    const event = new Event('dragleave', { bubbles: true, cancelable: true })
    Object.defineProperty(event, 'relatedTarget', { value: relatedTarget })
    fireEvent(el, event)
  }

  it('자식 요소로 향하는 dragleave는 드롭존이 계속 활성 상태를 유지한다 (깜박임 방지)', () => {
    mockAssets()
    render(<StyleView />)
    const zone = screen.getByTestId('tone-dropzone')
    const child = zone.querySelector('button')

    fireEvent.dragOver(zone, { dataTransfer: {} })
    // relatedTarget이 여전히 드롭존 내부(자식)인 경우 — 실제 이탈이 아니다
    dragLeaveWithRelatedTarget(zone, child)

    expect(zone.className).toContain('border-blue-400')
  })

  it('드롭존 밖으로 완전히 나가면 강조가 해제된다', () => {
    mockAssets()
    render(<StyleView />)
    const zone = screen.getByTestId('tone-dropzone')

    fireEvent.dragOver(zone, { dataTransfer: {} })
    dragLeaveWithRelatedTarget(zone, document.body)

    expect(zone.className).not.toContain('border-blue-400')
  })

  it('지원하지 않는 확장자를 드롭하면 업로드하지 않고 안내 문구를 보여준다', async () => {
    mockAssets()
    render(<StyleView />)
    await waitFor(() => screen.getByText('보고서_어투'))

    fireEvent.drop(screen.getByTestId('tone-dropzone'), {
      dataTransfer: { files: [new File(['x'], '악성코드.exe')] },
    })

    await waitFor(() => {
      expect(screen.getByText(/지원하지 않는 파일 형식/)).toBeInTheDocument()
    })
    expect(mockUploadRagAsset).not.toHaveBeenCalled()
  })
})

describe('업로드·삭제·보기 실패 시 인라인 에러 안내', () => {
  it('업로드 실패 시 에러 문구를 표시한다 (기존: 조용히 무시됨)', async () => {
    mockAssets()
    mockUploadRagAsset.mockRejectedValue(new Error('413'))
    render(<StyleView />)
    await waitFor(() => screen.getByText('보고서_어투'))

    fireEvent.drop(screen.getByTestId('tone-dropzone'), {
      dataTransfer: { files: [new File(['x'], '큰파일.docx')] },
    })

    await waitFor(() => {
      expect(screen.getByText(/업로드에 실패했습니다/)).toBeInTheDocument()
    })
  })

  it('삭제 실패 시 에러 문구를 표시한다', async () => {
    mockAssets()
    mockDeleteRagAsset.mockRejectedValue(new Error('network'))
    render(<StyleView />)
    await waitFor(() => screen.getByText('a.docx'))

    const row = screen.getByText('a.docx').closest('div[class*="flex items-center"]')
    fireEvent.click(row.querySelector('button:last-child'))

    await waitFor(() => {
      expect(screen.getByText(/삭제에 실패했습니다/)).toBeInTheDocument()
    })
  })

  it('[회귀] 성공 후에는 이전 에러 문구가 사라진다', async () => {
    mockAssets()
    mockUploadRagAsset.mockRejectedValueOnce(new Error('fail')).mockResolvedValueOnce({ id: 1 })
    render(<StyleView />)
    await waitFor(() => screen.getByText('보고서_어투'))

    fireEvent.drop(screen.getByTestId('tone-dropzone'), { dataTransfer: { files: [new File(['x'], 'a.docx')] } })
    await waitFor(() => expect(screen.getByText(/업로드에 실패했습니다/)).toBeInTheDocument())

    fireEvent.drop(screen.getByTestId('tone-dropzone'), { dataTransfer: { files: [new File(['x'], 'b.docx')] } })
    await waitFor(() => expect(screen.queryByText(/업로드에 실패했습니다/)).toBeNull())
  })
})

describe('워크스페이스 적용중 배지 (가짜 개념 제거)', () => {
  it('실데이터에 없는 개념이므로 배지가 렌더되지 않는다', async () => {
    mockAssets()
    render(<StyleView />)
    await waitFor(() => screen.getByText('보고서_어투'))
    expect(screen.queryByText('워크스페이스 적용중')).toBeNull()
  })
})
