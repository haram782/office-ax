/**
 * Login 베타 게이트 테스트 — 게스트 토큰 제거 + 베타 동의 화면.
 *
 * closed-beta-launch-plan-v1-ko.md M1 기준:
 *   - 하드코딩 게스트 토큰 버튼은 제거되어야 한다
 *   - 첫 로그인 시 동의 화면을 거쳐야만 토큰이 저장된다
 *   - 이미 동의한 사용자는 동의 화면 없이 진입한다
 *
 * Red → Green → Refactor
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'

// Ic 아이콘은 테스트 목적상 span으로 대체
vi.mock('../src/components/Ic', () => ({
  Ic: ({ name }) => <span data-testid={`ic-${name}`} />,
}))

// 테마 컨텍스트 대체 — Login이 useTheme를 직접 사용하므로 목 필요
vi.mock('../src/theme', () => ({
  useTheme: () => ({ theme: 'light', toggleTheme: vi.fn() }),
}))

// Google OAuth 훅 대체 — onSuccess를 테스트에서 직접 트리거할 수 있게 캡처
let capturedLoginConfig = null
vi.mock('@react-oauth/google', () => ({
  useGoogleLogin: (config) => {
    capturedLoginConfig = config
    return () => {} // 실제 팝업은 열지 않는다
  },
}))

// 백엔드 로그인 API 대체
const logoutMock = vi.fn().mockResolvedValue(undefined)
vi.mock('../src/api/client', () => ({
  googleLogin: vi.fn().mockResolvedValue({
    token: 'drf-token-abc',
    user: { id: 1, email: 'invited@example.com', name: '초대유저', picture: '' },
  }),
  logout: (...args) => logoutMock(...args),
}))

import Login from '../src/pages/Login'

function renderLogin() {
  return render(
    <MemoryRouter>
      <Login />
    </MemoryRouter>
  )
}

/** Google 로그인 성공을 시뮬레이션한다 (버튼 클릭 → onSuccess 콜백 실행) */
async function simulateGoogleSuccess() {
  fireEvent.click(screen.getByText(/Google 계정으로 시작하기/))
  await capturedLoginConfig.onSuccess({ access_token: 'google-access-token' })
}

beforeEach(() => {
  localStorage.clear()
  capturedLoginConfig = null
  logoutMock.mockClear()
})

describe('게스트 토큰 제거', () => {
  it('하드코딩된 게스트 계정 버튼이 렌더링되지 않는다', () => {
    renderLogin()
    expect(screen.queryByText(/게스트1로 시작/)).toBeNull()
    expect(screen.queryByText(/게스트2로 시작/)).toBeNull()
    expect(screen.queryByText(/테스트 모드/)).toBeNull()
  })
})

describe('베타 동의 화면', () => {
  it('첫 로그인 성공 시 동의 화면이 뜨고, 동의 전에는 토큰을 저장하지 않는다', async () => {
    renderLogin()
    await simulateGoogleSuccess()

    // 동의 화면 핵심 고지 문구 노출
    await waitFor(() => {
      expect(screen.getByText(/외부 LLM API/)).toBeInTheDocument()
    })
    expect(screen.getByText(/30일 후 자동 삭제/)).toBeInTheDocument()
    // 동의 전에는 인증 토큰이 저장되면 안 된다 (동의 우회 방지)
    expect(localStorage.getItem('auth_token')).toBeNull()
  })

  it('동의 버튼을 누르면 토큰·동의 플래그를 저장한다', async () => {
    renderLogin()
    await simulateGoogleSuccess()
    await waitFor(() => {
      expect(screen.getByText(/동의하고 시작하기/)).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText(/동의하고 시작하기/))

    await waitFor(() => {
      expect(localStorage.getItem('auth_token')).toBe('drf-token-abc')
    })
    expect(localStorage.getItem('ax_beta_consent')).toBeTruthy()
    expect(JSON.parse(localStorage.getItem('ax_user')).email).toBe('invited@example.com')
  })

  it('동의하지 않으면 토큰을 저장하지 않고 초기 화면으로 돌아간다', async () => {
    renderLogin()
    await simulateGoogleSuccess()
    await waitFor(() => {
      expect(screen.getByText(/동의하지 않음/)).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText(/동의하지 않음/))

    await waitFor(() => expect(logoutMock).toHaveBeenCalledWith('drf-token-abc'))
    expect(localStorage.getItem('auth_token')).toBeNull()
    expect(localStorage.getItem('ax_beta_consent')).toBeNull()
    // 초기 로그인 버튼으로 복귀
    expect(screen.getByText(/Google 계정으로 시작하기/)).toBeInTheDocument()
  })

  it('[회귀] 이미 동의한 사용자는 동의 화면 없이 바로 토큰이 저장된다', async () => {
    localStorage.setItem('ax_beta_consent', 'v1')
    renderLogin()
    await simulateGoogleSuccess()

    await waitFor(() => {
      expect(localStorage.getItem('auth_token')).toBe('drf-token-abc')
    })
    expect(screen.queryByText(/동의하고 시작하기/)).toBeNull()
  })
})
