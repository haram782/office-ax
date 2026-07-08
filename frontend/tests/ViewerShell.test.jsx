/**
 * ViewerShell 컴포넌트 단위 테스트
 *
 * Red → Green → Refactor 사이클 문서:
 *   Red:    ViewerShell.jsx 없는 상태에서 실행 → 모두 실패
 *   Green:  ViewerShell.jsx 구현 후 → 모두 통과
 *   Refactor: WorkspaceCenter/PreviewPage에서 ViewerShell 사용
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ViewerShell } from '../src/components/ViewerShell'

describe('ViewerShell', () => {
  it('filename을 헤더에 렌더한다', () => {
    render(
      <ViewerShell filename="보고서.xlsx" onClose={null} onNewWindow={null}>
        <div>뷰어 콘텐츠</div>
      </ViewerShell>,
    )
    expect(screen.getByText('보고서.xlsx')).toBeInTheDocument()
  })

  it('children을 뷰어 영역에 렌더한다', () => {
    render(
      <ViewerShell filename="test.pdf" onClose={null} onNewWindow={null}>
        <div data-testid="viewer-content">PDF 뷰어</div>
      </ViewerShell>,
    )
    expect(screen.getByTestId('viewer-content')).toBeInTheDocument()
  })

  it('sidePanel이 있으면 렌더한다', () => {
    render(
      <ViewerShell filename="test.xlsx" onClose={null} onNewWindow={null} sidePanel={<aside data-testid="side-panel">패널</aside>}>
        <div>뷰어</div>
      </ViewerShell>,
    )
    expect(screen.getByTestId('side-panel')).toBeInTheDocument()
  })

  it('sidePanel이 null이면 렌더하지 않는다', () => {
    render(
      <ViewerShell filename="test.xlsx" onClose={null} onNewWindow={null} sidePanel={null}>
        <div>뷰어</div>
      </ViewerShell>,
    )
    // data-testid로 찾으면 없어야 한다
    expect(screen.queryByTestId('side-panel')).not.toBeInTheDocument()
  })

  it('onClose가 있으면 닫기 버튼이 렌더되고 클릭 시 호출된다', async () => {
    const onClose = vi.fn()
    render(
      <ViewerShell filename="test.docx" onClose={onClose} onNewWindow={null}>
        <div>뷰어</div>
      </ViewerShell>,
    )
    const closeBtn = screen.getByRole('button', { name: /닫기|close/i })
    await userEvent.click(closeBtn)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('onClose가 null이면 닫기 버튼이 렌더되지 않는다', () => {
    render(
      <ViewerShell filename="test.docx" onClose={null} onNewWindow={null}>
        <div>뷰어</div>
      </ViewerShell>,
    )
    expect(screen.queryByRole('button', { name: /닫기|close/i })).not.toBeInTheDocument()
  })

  it('headerExtra가 있으면 헤더에 렌더한다', () => {
    render(
      <ViewerShell filename="test.hwp" onClose={null} onNewWindow={null} headerExtra={<span data-testid="header-logo">AX</span>}>
        <div>뷰어</div>
      </ViewerShell>,
    )
    expect(screen.getByTestId('header-logo')).toBeInTheDocument()
  })

  it('headerExtra가 null이면 추가 요소가 없다', () => {
    render(
      <ViewerShell filename="test.hwp" onClose={null} onNewWindow={null} headerExtra={null}>
        <div>뷰어</div>
      </ViewerShell>,
    )
    expect(screen.queryByTestId('header-logo')).not.toBeInTheDocument()
  })

  it('versionPanel이 있으면 툴바 아래에 렌더한다', () => {
    render(
      <ViewerShell filename="test.hwp" onClose={null} onNewWindow={null} versionPanel={<div data-testid="version-panel">버전 탭</div>}>
        <div>뷰어</div>
      </ViewerShell>,
    )

    expect(screen.getByTestId('version-panel')).toBeInTheDocument()
  })

  it('onNewWindow가 있으면 새 창 버튼이 렌더되고 클릭 시 호출된다', async () => {
    const onNewWindow = vi.fn()
    render(
      <ViewerShell filename="test.xlsx" onClose={null} onNewWindow={onNewWindow}>
        <div>뷰어</div>
      </ViewerShell>,
    )
    const btn = screen.getByRole('button', { name: /새 창/i })
    await userEvent.click(btn)
    expect(onNewWindow).toHaveBeenCalledTimes(1)
  })

  it('onNewWindow가 null이면 새 창 버튼이 없다', () => {
    render(
      <ViewerShell filename="test.xlsx" onClose={null} onNewWindow={null}>
        <div>뷰어</div>
      </ViewerShell>,
    )
    expect(screen.queryByRole('button', { name: /새 창/i })).not.toBeInTheDocument()
  })
})
