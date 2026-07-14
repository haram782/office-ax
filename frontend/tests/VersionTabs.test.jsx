/**
 * VersionTabs 컴포넌트 단위 테스트
 * Red → Green → Refactor TDD
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { VersionTabs } from '../src/pages/Workspace/VersionTabs'

const VERSIONS = [
  { id: 1, version_number: 1, status: 'original',   label: '원본',   created_at: '2026-07-08T05:10:00' },
  { id: 2, version_number: 2, status: 'ready',      label: '수정본', created_at: '2026-07-08T05:20:00', updated_at: '2026-07-08T05:25:00' },
  { id: 3, version_number: 3, status: 'generating', label: '생성 중', created_at: '2026-07-08T05:30:00' },
]

describe('VersionTabs', () => {
  it('버전 배열이 없으면 원본 탭만 표시된다', () => {
    render(<VersionTabs versions={[]} selectedVersionId={null} onSelectVersion={vi.fn()} />)

    expect(screen.getByText('원본')).toBeInTheDocument()
    expect(screen.getByText('v1')).toBeInTheDocument()
    // ready/generating 탭 없음
    expect(screen.queryByText('수정본')).not.toBeInTheDocument()
  })

  it('selectedVersionId에 해당하는 탭이 active 스타일을 가진다', () => {
    render(
      <VersionTabs
        versions={VERSIONS}
        selectedVersionId={1}
        onSelectVersion={vi.fn()}
      />,
    )
    // id=1 (원본) 탭 버튼이 aria-pressed 또는 data-active 속성으로 식별 가능
    // 또는 role=tab + aria-selected 사용
    const activeTab = screen.getByRole('button', { name: /원본/ })
    expect(activeTab).toHaveAttribute('data-active', 'true')
  })

  it('ready 탭 클릭 시 onSelectVersion이 해당 버전 객체로 호출된다', async () => {
    const onSelectVersion = vi.fn()
    render(
      <VersionTabs
        versions={VERSIONS}
        selectedVersionId={1}
        onSelectVersion={onSelectVersion}
      />,
    )

    await userEvent.click(screen.getByRole('button', { name: /수정본/ }))

    expect(onSelectVersion).toHaveBeenCalledWith(VERSIONS[1])
  })

  it('탭에 버전 번호와 날짜 시간이 함께 표시된다', () => {
    render(<VersionTabs versions={VERSIONS} selectedVersionId={1} onSelectVersion={vi.fn()} />)

    expect(screen.getByText(/v2 ·/)).toBeInTheDocument()
    expect(screen.getByText(/05:25/)).toBeInTheDocument()
    expect(screen.getByText('완료')).toBeInTheDocument()
  })

  it('generating 상태 탭은 disabled이다', () => {
    render(
      <VersionTabs
        versions={VERSIONS}
        selectedVersionId={1}
        onSelectVersion={vi.fn()}
      />,
    )
    // 생성 중 탭은 클릭 불가
    const generatingTab = screen.getByRole('button', { name: /생성 중/ })
    expect(generatingTab).toBeDisabled()
  })

  it('+ 새 버전 버튼이 없다', () => {
    render(<VersionTabs versions={VERSIONS} selectedVersionId={1} onSelectVersion={vi.fn()} />)

    expect(screen.queryByText(/새 버전/)).not.toBeInTheDocument()
  })

  it('generating 탭에 스피너 요소가 렌더된다', () => {
    const { container } = render(
      <VersionTabs versions={VERSIONS} selectedVersionId={1} onSelectVersion={vi.fn()} />,
    )
    // animate-spin 클래스를 가진 요소가 있어야 한다
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('change 안내가 없을 때 version-level 안전 문구를 fallback으로 표시한다', () => {
    render(
      <VersionTabs
        versions={VERSIONS}
        selectedVersionId={1}
        onSelectVersion={vi.fn()}
        fallbackFailureMessage="원본 파일을 읽지 못했습니다. 파일을 다시 업로드해 주세요."
      />,
    )

    expect(screen.getByRole('alert')).toHaveTextContent('원본 파일을 읽지 못했습니다')
  })

  it('ambiguous_anchor version fallback은 실패 alert가 아닌 확인 필요 status로 표시한다', () => {
    render(
      <VersionTabs
        versions={VERSIONS}
        selectedVersionId={1}
        onSelectVersion={vi.fn()}
        fallbackFailureCode="ambiguous_anchor"
        fallbackFailureMessage="수정할 위치가 여러 곳입니다. 위치 단서를 더해 다시 요청해 주세요."
      />,
    )

    expect(screen.getByRole('status')).toHaveTextContent('위치 단서를 더해 다시 요청해 주세요')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
