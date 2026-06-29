/**
 * PdfViewer 컴포넌트 테스트
 * Red → Green → Refactor TDD 사이클
 */

import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// ── pdfjs-dist 전체 모킹 — vi.mock은 호이스팅되어 import보다 먼저 실행됨 ──
const mockGetDocument = vi.fn()
vi.mock('pdfjs-dist', () => ({
  GlobalWorkerOptions: { workerSrc: '' },
  getDocument: (...args) => mockGetDocument(...args),
}))

// ── @rhwp/core 모킹 — DocumentPanel 상단에서 import하므로 함께 모킹 ──
vi.mock('@rhwp/core', () => ({
  default: vi.fn().mockResolvedValue(undefined),
  HwpDocument: vi.fn(),
}))

// 실제 PDF 페이지 mock 생성 헬퍼
function makeMockDoc(numPages = 3) {
  const mockPage = {
    getViewport: vi.fn(() => ({ width: 595, height: 842 })),
    render: vi.fn(() => ({ promise: Promise.resolve(), cancel: vi.fn() })),
  }
  return {
    numPages,
    getPage: vi.fn().mockResolvedValue(mockPage),
    destroy: vi.fn(),
  }
}

// resolveViewer는 PDF previewData를 받아 PdfViewer 엘리먼트를 반환함
import { resolveViewer } from '../src/components/DocumentPanel'

function renderPdf(fileUrl, snippetData = null) {
  const previewData = { filename: 'test.pdf', fileUrl, snippetData }
  return render(resolveViewer(previewData, {}))
}

// ── HTMLCanvasElement stub — happy-dom에 canvas 미구현 ──
beforeEach(() => {
  vi.stubGlobal('HTMLCanvasElement', class {
    getContext() { return { scale: vi.fn(), fillRect: vi.fn() } }
  })
  Object.defineProperty(HTMLCanvasElement.prototype, 'getContext', {
    value: vi.fn(() => ({ scale: vi.fn(), fillRect: vi.fn() })),
    configurable: true,
  })
  mockGetDocument.mockReset()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('PdfViewer — empty state', () => {
  it('fileUrl 없을 때 대기 안내 텍스트를 표시한다', () => {
    renderPdf(null)
    expect(screen.getByText(/PDF 미리보기를 준비 중입니다/)).toBeTruthy()
  })
})

describe('PdfViewer — loading state', () => {
  it('fileUrl 있고 getDocument pending일 때 스피너를 표시한다', () => {
    // getDocument가 영원히 pending인 promise 반환
    mockGetDocument.mockReturnValue({ promise: new Promise(() => {}) })

    renderPdf('/media/test.pdf')

    expect(screen.getByText('PDF를 불러오는 중…')).toBeTruthy()
  })
})

describe('PdfViewer — error state', () => {
  it('getDocument reject 시 에러 메시지를 표시한다', async () => {
    mockGetDocument.mockReturnValue({
      promise: Promise.reject(new Error('파일 손상')),
    })

    await act(async () => {
      renderPdf('/media/broken.pdf')
    })

    await waitFor(() => {
      expect(screen.getByText('PDF를 열지 못했습니다')).toBeTruthy()
    })
    expect(screen.getByText('파일 손상')).toBeTruthy()
  })
})

describe('PdfViewer — done state', () => {
  it('getDocument resolve 시 페이지 내비게이터를 표시한다', async () => {
    const mockDoc = makeMockDoc(5)
    mockGetDocument.mockReturnValue({ promise: Promise.resolve(mockDoc) })

    await act(async () => {
      renderPdf('/media/sample.pdf')
    })

    await waitFor(() => {
      // "1 / 5" 형태로 현재 페이지 / 전체 페이지 표시
      expect(screen.getByText('/ 5')).toBeTruthy()
    })
  })

  it('초기 줌 표시가 100%다', async () => {
    const mockDoc = makeMockDoc(2)
    mockGetDocument.mockReturnValue({ promise: Promise.resolve(mockDoc) })

    await act(async () => {
      renderPdf('/media/sample.pdf')
    })

    await waitFor(() => {
      expect(screen.getByText('100%')).toBeTruthy()
    })
  })

  it('줌 인 버튼 클릭 시 125%로 증가한다', async () => {
    const mockDoc = makeMockDoc(2)
    mockGetDocument.mockReturnValue({ promise: Promise.resolve(mockDoc) })

    await act(async () => {
      renderPdf('/media/sample.pdf')
    })

    await waitFor(() => { expect(screen.getByText('100%')).toBeTruthy() })

    const zoomInBtn = screen.getByText('+')
    await act(async () => { fireEvent.click(zoomInBtn) })

    expect(screen.getByText('125%')).toBeTruthy()
  })

  it('줌 아웃 버튼 클릭 시 75%로 감소한다', async () => {
    const mockDoc = makeMockDoc(2)
    mockGetDocument.mockReturnValue({ promise: Promise.resolve(mockDoc) })

    await act(async () => {
      renderPdf('/media/sample.pdf')
    })

    await waitFor(() => { expect(screen.getByText('100%')).toBeTruthy() })

    const zoomOutBtn = screen.getByText('−')
    await act(async () => { fireEvent.click(zoomOutBtn) })

    expect(screen.getByText('75%')).toBeTruthy()
  })

  it('이전 페이지 버튼은 첫 페이지에서 비활성화된다', async () => {
    const mockDoc = makeMockDoc(3)
    mockGetDocument.mockReturnValue({ promise: Promise.resolve(mockDoc) })

    await act(async () => {
      renderPdf('/media/sample.pdf')
    })

    await waitFor(() => { expect(screen.getByText('/ 3')).toBeTruthy() })

    // SVG 기반 이전 버튼: disabled 속성 확인
    const buttons = screen.getAllByRole('button')
    const prevBtn = buttons.find(b => b.disabled !== undefined && b.disabled)
    expect(prevBtn).toBeTruthy()
  })
})
