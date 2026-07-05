/**
 * RAG 실데이터 연결 테스트 (점검 발견 A-2).
 *
 * 기존: getRagAssets 목업 + RagSelector 옵션 하드코딩 + 선택이 채팅으로 미전달.
 * 변경: 실제 /rag-assets/ 연동, 그룹핑, 업로드, 채팅 전송 시 rag_asset_ids 포함.
 *
 * Red → Green → Refactor
 */

import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('../src/components/Ic', () => ({
  Ic: ({ name }) => <span data-testid={`ic-${name}`} />,
}))

const mockGet = vi.hoisted(() => vi.fn())
const mockPost = vi.hoisted(() => vi.fn())
vi.mock('axios', () => ({
  default: {
    create: () => ({
      get: mockGet,
      post: mockPost,
      interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
    }),
  },
}))

import { getRagAssets, uploadRagAsset, sendChatMessage } from '../src/api/client'
import { RagSelector } from '../src/pages/Workspace/RagSelector'

const ASSETS = [
  { id: 11, kind: 'tone', group_name: '보고서_어투', file: '/media/rag/a.docx', file_size: 1024, trained: true },
  { id: 12, kind: 'tone', group_name: '보고서_어투', file: '/media/rag/b.docx', file_size: 2048, trained: true },
  { id: 21, kind: 'form', group_name: '계약서_양식', file: '/media/rag/c.hwp', file_size: 512, trained: false },
]

beforeEach(() => { vi.clearAllMocks() })

describe('getRagAssets 실연결·그룹핑', () => {
  it('/rag-assets/를 호출하고 kind·group_name으로 그룹핑한다', async () => {
    mockGet.mockResolvedValue({ data: ASSETS })
    const { tones, forms } = await getRagAssets()

    expect(mockGet).toHaveBeenCalledWith('/rag-assets/')
    expect(tones).toHaveLength(1)
    expect(tones[0].name).toBe('보고서_어투')
    expect(tones[0].assetIds).toEqual([11, 12])
    expect(forms[0].name).toBe('계약서_양식')
    expect(forms[0].assetIds).toEqual([21])
  })
})

describe('uploadRagAsset', () => {
  it('kind·group_name·file을 multipart로 POST한다', async () => {
    mockPost.mockResolvedValue({ data: { id: 99 } })
    const file = new File(['x'], '새_어투.docx')

    await uploadRagAsset('tone', '새_어투', file)

    const [url, form] = mockPost.mock.calls[0]
    expect(url).toBe('/rag-assets/')
    expect(form.get('kind')).toBe('tone')
    expect(form.get('group_name')).toBe('새_어투')
    expect(form.get('file')).toBe(file)
  })
})

describe('sendChatMessage rag_asset_ids', () => {
  it('선택된 자산 id 배열을 rag_asset_ids로 포함한다', async () => {
    mockPost.mockResolvedValue({ data: { message_id: 1 } })
    await sendChatMessage(5, '어투 적용해줘', null, 10, [11, 12])

    const form = mockPost.mock.calls[0][1]
    expect(JSON.parse(form.get('rag_asset_ids'))).toEqual([11, 12])
  })

  it('[회귀] 선택이 없으면 rag_asset_ids 필드를 보내지 않는다', async () => {
    mockPost.mockResolvedValue({ data: { message_id: 1 } })
    await sendChatMessage(5, '일반 질문', null, 10)

    const form = mockPost.mock.calls[0][1]
    expect(form.get('rag_asset_ids')).toBeNull()
  })
})

describe('RagSelector 실데이터', () => {
  const toneGroups = [{ name: '보고서_어투', assetIds: [11, 12] }]
  const formGroups = [{ name: '계약서_양식', assetIds: [21] }]

  it('props로 받은 실제 그룹을 옵션으로 렌더한다 (하드코딩 제거)', () => {
    render(
      <RagSelector
        toneGroups={toneGroups}
        formGroups={formGroups}
        ragTone=""
        ragForm=""
        onToneChange={vi.fn()}
        onFormChange={vi.fn()}
        onUpload={vi.fn()}
      />
    )
    expect(screen.getByText('보고서_어투')).toBeInTheDocument()
    expect(screen.getByText('계약서_양식')).toBeInTheDocument()
    expect(screen.queryByText('하람_보고서_스타일')).toBeNull()
  })

  it('그룹이 없으면 "미지정" 옵션만 표시된다', () => {
    render(
      <RagSelector
        toneGroups={[]}
        formGroups={[]}
        ragTone=""
        ragForm=""
        onToneChange={vi.fn()}
        onFormChange={vi.fn()}
        onUpload={vi.fn()}
      />
    )
    expect(screen.getAllByText('미지정')).toHaveLength(2)
  })
})
