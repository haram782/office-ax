/**
 * PatchRequestInput 컴포넌트 단위 테스트
 * Red → Green → Refactor TDD
 */

import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { PatchRequestInput } from '../src/pages/Workspace/PatchRequestInput'

describe('PatchRequestInput', () => {
  it('uploadId 없으면 입력창이 렌더되지 않는다', () => {
    const { container } = render(
      <PatchRequestInput uploadId={null} onGenerate={vi.fn()} isGenerating={false} />,
    )
    expect(container.firstChild).toBeNull()
  })

  it('uploadId 있으면 textarea가 렌더된다', () => {
    render(
      <PatchRequestInput uploadId={10} onGenerate={vi.fn()} isGenerating={false} />,
    )
    expect(screen.getByRole('textbox')).toBeInTheDocument()
  })

  it('전송 버튼 클릭 시 입력된 텍스트로 onGenerate가 호출된다', () => {
    const onGenerate = vi.fn()
    render(
      <PatchRequestInput uploadId={10} onGenerate={onGenerate} isGenerating={false} />,
    )

    const textarea = screen.getByRole('textbox')
    fireEvent.change(textarea, { target: { value: '표 헤더를 굵게' } })
    fireEvent.click(screen.getByRole('button'))

    expect(onGenerate).toHaveBeenCalledWith('표 헤더를 굵게')
  })

  it('isGenerating=true일 때 버튼이 비활성화된다', () => {
    render(
      <PatchRequestInput uploadId={10} onGenerate={vi.fn()} isGenerating={true} />,
    )
    expect(screen.getByRole('button')).toBeDisabled()
  })

  it('빈 입력으로는 전송이 불가하다 (버튼 비활성화)', () => {
    render(
      <PatchRequestInput uploadId={10} onGenerate={vi.fn()} isGenerating={false} />,
    )
    // 입력값 없으면 버튼 비활성
    expect(screen.getByRole('button')).toBeDisabled()
  })
})
