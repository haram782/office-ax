import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'

import { Topbar } from '../src/components/Topbar'

const logoutMock = vi.fn()
vi.mock('../src/api/client', () => ({ logout: () => logoutMock() }))
vi.mock('../src/theme', () => ({ useTheme: () => ({ theme: 'light', toggleTheme: vi.fn() }) }))

describe('Topbar logout', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('auth_token', 'token')
    localStorage.setItem('ax_user', JSON.stringify({ name: '사용자' }))
    logoutMock.mockReset()
  })

  it('서버 logout을 호출하고 성공 여부와 무관하게 로컬 인증을 제거한다', async () => {
    logoutMock.mockRejectedValueOnce(new Error('network'))
    render(<MemoryRouter initialEntries={['/workspace']}><Topbar onNewConversation={() => {}} /></MemoryRouter>)
    await userEvent.click(screen.getByTitle('로그아웃'))
    await waitFor(() => expect(logoutMock).toHaveBeenCalledOnce())
    expect(localStorage.getItem('auth_token')).toBeNull()
    expect(localStorage.getItem('ax_user')).toBeNull()
    expect(screen.getByRole('status')).toHaveTextContent('서버 세션 종료')
  })
})
