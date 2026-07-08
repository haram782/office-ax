import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { ChatInput } from '../src/components/ChatInput'

describe('ChatInput 파일 첨부', () => {
  it('파일 미선택 안내 상태에서도 첨부 버튼은 활성화된다', () => {
    render(<ChatInput onSend={vi.fn()} isProcessing={false} disabled />)

    expect(screen.getByRole('button', { name: '파일 첨부' })).not.toBeDisabled()
    expect(screen.getByPlaceholderText('메시지를 입력하세요…')).toBeDisabled()
  })

  it('텍스트 입력이 막힌 상태에서도 파일 선택 후 파일만 전송할 수 있다', async () => {
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} isProcessing={false} disabled />)

    const file = new File(['hello'], 'sample.hwp', { type: 'application/octet-stream' })
    const input = document.querySelector('input[type="file"]')

    fireEvent.change(input, { target: { files: [file] } })
    await userEvent.click(screen.getByRole('button', { name: '전송' }))

    expect(onSend).toHaveBeenCalledWith('', [file])
  })
})
