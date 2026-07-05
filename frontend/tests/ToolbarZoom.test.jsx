/**
 * 뷰어 툴바 정리 테스트 (점검 발견 A-4).
 *
 *   - 줌 컨트롤이 실제로 콘텐츠에 scale로 반영된다 (기존: 로컬 state만 변경)
 *   - 동작 없는 장식 컨트롤(회전·메뉴·페이지 1/1)은 제거된다
 *
 * Red → Green → Refactor
 */

import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'

vi.mock('../src/components/Ic', () => ({
  Ic: ({ name }) => <span data-testid={`ic-${name}`} />,
}))

import { ViewerShell } from '../src/components/ViewerShell'

function renderShell() {
  return render(
    <ViewerShell filename="doc.xlsx">
      <div>문서 내용</div>
    </ViewerShell>
  )
}

describe('뷰어 줌', () => {
  it('+ 버튼을 누르면 콘텐츠 래퍼에 scale이 반영된다', () => {
    renderShell()
    const plus = screen.getByTestId('ic-plus').closest('button')
    fireEvent.click(plus)

    const wrapper = screen.getByTestId('viewer-zoom-wrapper')
    expect(wrapper.style.transform).toContain('scale(1.25)')
    expect(screen.getByText('125%')).toBeInTheDocument()
  })

  it('- 버튼은 최소 25%까지만 줄어든다 (경계)', () => {
    renderShell()
    const minus = screen.getByTestId('ic-minus').closest('button')
    for (let i = 0; i < 10; i++) fireEvent.click(minus)
    expect(screen.getByText('25%')).toBeInTheDocument()
  })

  it('기본 100%에서는 scale 변형을 걸지 않는다', () => {
    renderShell()
    const wrapper = screen.getByTestId('viewer-zoom-wrapper')
    expect(wrapper.style.transform ?? '').not.toContain('scale')
  })
})

describe('장식 컨트롤 제거', () => {
  it('회전·메뉴 버튼과 하드코딩 페이지 표시(1 / 1)가 렌더되지 않는다', () => {
    renderShell()
    expect(screen.queryByTestId('ic-rotate')).toBeNull()
    expect(screen.queryByTestId('ic-menu')).toBeNull()
    expect(screen.queryByText('/ 1')).toBeNull()
  })
})
