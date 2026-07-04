import { Routes, Route, Navigate } from 'react-router-dom'
import CreditLimitModal from './components/CreditLimitModal'
import Login      from './pages/Login'
import Dashboard  from './pages/Dashboard'
import Workspace  from './pages/Workspace'
import Pipeline   from './pages/Pipeline'
import PreviewPage from './pages/PreviewPage'

/**
 * 인증 가드 — localStorage에 auth_token이 없으면 /login으로 리다이렉트한다.
 */
function RequireAuth({ children }) {
  const token = localStorage.getItem('auth_token')
  if (!token) return <Navigate to="/login" replace />
  return children
}

/**
 * 라우트 정의.
 * ThemeProvider의 dark 래퍼 내부에서 렌더된다.
 */
export default function App() {
  return (
    <div className="min-h-screen bg-zinc-100 dark:bg-zinc-950 text-zinc-800 dark:text-zinc-300">
      {/* 크레딧 소진(429) 전역 안내 — api/client.js 인터셉터 이벤트 수신 */}
      <CreditLimitModal />
      <Routes>
        <Route path="/login" element={<Login />} />
        {/* 대시보드만 인증 필수 */}
        <Route path="/"             element={<RequireAuth><Dashboard /></RequireAuth>} />
        <Route path="/workspace"    element={<Workspace />} />
        <Route path="/pipeline/:id" element={<Pipeline />} />
        <Route path="/preview"      element={<PreviewPage />} />
      </Routes>
    </div>
  )
}
