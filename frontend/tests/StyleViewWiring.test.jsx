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

describe('워크스페이스 적용중 배지 (가짜 개념 제거)', () => {
  it('실데이터에 없는 개념이므로 배지가 렌더되지 않는다', async () => {
    mockAssets()
    render(<StyleView />)
    await waitFor(() => screen.getByText('보고서_어투'))
    expect(screen.queryByText('워크스페이스 적용중')).toBeNull()
  })
})
