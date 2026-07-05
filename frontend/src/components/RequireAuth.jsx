import { Navigate } from 'react-router-dom'

/**
 * 인증 가드 — localStorage에 auth_token이 없으면 /login으로 리다이렉트한다.
 * 게스트 토큰 제거 이후 모든 사용자 페이지 라우트를 이 컴포넌트로 감싼다.
 */
export function RequireAuth({ children }) {
  const token = localStorage.getItem('auth_token')
  if (!token) return <Navigate to="/login" replace />
  return children
}
