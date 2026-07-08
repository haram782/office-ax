import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { WorkspaceChat } from '../src/pages/Workspace/WorkspaceChat'

const baseProps = {
  messages: [],
  isProcessing: false,
  error: null,
  onFileView: vi.fn(),
  uploadId: null,
  onChatAcceptAll: vi.fn(),
  ragTone: '',
  ragForm: '',
  onRagToneChange: vi.fn(),
  onRagFormChange: vi.fn(),
  ragToneGroups: [],
  ragFormGroups: [],
  onRagUpload: vi.fn(),
  ragAssetIds: [],
  activeConvTitle: '새 대화',
  onNewConversation: vi.fn(),
}

describe('WorkspaceChat 파일 없는 채팅', () => {
  it('파일 없이도 텍스트 입력과 전송이 가능하다', async () => {
    const onSend = vi.fn()
    render(<WorkspaceChat {...baseProps} onSend={onSend} />)

    const input = screen.getByPlaceholderText('메시지를 입력하세요…')
    expect(input).not.toBeDisabled()
    expect(screen.queryByText('파일을 먼저 선택해주세요')).not.toBeInTheDocument()

    await userEvent.type(input, '일반 질문')
    await userEvent.click(screen.getByRole('button', { name: '전송' }))

    expect(onSend).toHaveBeenCalledWith('일반 질문', [], null, [])
  })
})
