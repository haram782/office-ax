/**
 * RequireAuth 인증 가드 테스트.
 *
 * 리뷰 발견 2 반영: 게스트 토큰 제거 이후 모든 사용자 페이지(/workspace 등)가
 * RequireAuth로 보호된다. 라우트 배선 자체는 Workspace 임포트 체인의
 * wasm 로딩 제약으로 여기서 검증할 수 없어, 가드 컴포넌트 동작만 고정한다.
 */

import { render, screen } from '@testing-library/react'
import { describe, it, expect, beforeEach } from 'vitest'
import { MemoryRouter, Routes, Route } from 'react-router-dom'

import { RequireAuth } from '../src/components/RequireAuth'

function renderGuarded() {
  return render(
    <MemoryRouter initialEntries={['/protected']}>
      <Routes>
        <Route path="/login" element={<div>로그인 페이지</div>} />
        <Route
          path="/protected"
          element={
            <RequireAuth>
              <div>보호된 콘텐츠</div>
            </RequireAuth>
          }
        />
      </Routes>
    </MemoryRouter>
  )
}

beforeEach(() => {
  localStorage.clear()
})

describe('RequireAuth', () => {
  it('토큰이 없으면 /login으로 리다이렉트한다', () => {
    renderGuarded()
    expect(screen.getByText('로그인 페이지')).toBeInTheDocument()
    expect(screen.queryByText('보호된 콘텐츠')).toBeNull()
  })

  it('토큰이 있으면 자식 콘텐츠를 렌더링한다', () => {
    localStorage.setItem('auth_token', 'valid-token')
    renderGuarded()
    expect(screen.getByText('보호된 콘텐츠')).toBeInTheDocument()
  })
})
