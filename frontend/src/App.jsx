import { Routes, Route } from 'react-router-dom'
import CreditLimitModal from './components/CreditLimitModal'
import { RequireAuth } from './components/RequireAuth'
import Login      from './pages/Login'
import Dashboard  from './pages/Dashboard'
import Workspace  from './pages/Workspace'
import Pipeline   from './pages/Pipeline'
import PreviewPage from './pages/PreviewPage'

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
        {/* 게스트 토큰 제거 이후 모든 사용자 페이지는 인증 필수 — 비로그인 시 깨진 화면 대신 로그인으로 유도 */}
        <Route path="/"             element={<RequireAuth><Dashboard /></RequireAuth>} />
        <Route path="/workspace"    element={<RequireAuth><Workspace /></RequireAuth>} />
        <Route path="/pipeline/:id" element={<RequireAuth><Pipeline /></RequireAuth>} />
        <Route path="/preview"      element={<RequireAuth><PreviewPage /></RequireAuth>} />
      </Routes>
    </div>
  )
}
