import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { Ic } from './Ic'
import { useTheme } from '../theme'

/** localStorage에서 유저 정보 파싱 */
function getStoredUser() {
  try { return JSON.parse(localStorage.getItem('ax_user') || 'null') } catch { return null }
}

/**
 * 전역 상단 네비게이션 바.
 * Dashboard / Workspace 페이지가 공유한다. Pipeline은 별도 헤더를 사용한다.
 *
 * @param {{ onNewConversation: () => void }} props
 */
export function Topbar({ onNewConversation }) {
  const navigate  = useNavigate()
  const { pathname } = useLocation()
  const { theme, toggleTheme } = useTheme()

  // 활성 탭 판별
  const isDashboard  = pathname === '/'
  const isWorkspace  = pathname === '/workspace'

  const pageTitle = isDashboard ? '통합 대시보드' : isWorkspace ? 'AI 문서 분석 워크스페이스' : ''

  // 인증 상태 — state로 관리해야 워크스페이스 로그아웃 시 리렌더가 발생한다
  const [token, setToken] = useState(() => localStorage.getItem('auth_token'))
  const [user,  setUser]  = useState(() => getStoredUser())

  /** 로그아웃 — 대시보드면 워크스페이스로 이동, 워크스페이스면 그 자리에서 리렌더 */
  const handleLogout = () => {
    localStorage.removeItem('auth_token')
    localStorage.removeItem('ax_user')
    setToken(null)
    setUser(null)
    if (isDashboard) navigate('/workspace', { replace: true })
  }

  /** 네비게이션 탭 버튼 */
  function NavBtn({ to, icon, label, active }) {
    return (
      <button
        onClick={() => navigate(to)}
        className={
          'inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium ' +
          (active
            ? 'bg-blue-50 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300'
            : 'text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800')
        }
      >
        <Ic name={icon} />
        {label}
      </button>
    )
  }

  return (
    <header className="h-14 shrink-0 flex items-center gap-3 px-4 border-b border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900">
      {/* 로고 */}
      <div className="flex items-center gap-2">
        <div className="w-8 h-8 rounded-lg bg-blue-600 text-white grid place-items-center font-bold text-xs">
          AX
        </div>
        <span className="font-bold text-zinc-800 dark:text-zinc-100">Office-AX</span>
      </div>

      {/* 구분선 */}
      <div className="h-5 w-px bg-zinc-200 dark:bg-zinc-700" />

      {/* 현재 페이지 제목 */}
      <span className="text-sm text-zinc-400 dark:text-zinc-500">{pageTitle}</span>

      <div className="flex-1" />

      {/* 메인 네비게이션 */}
      <nav className="flex items-center gap-1">
        <NavBtn to="/"          icon="layout"   label="대시보드"    active={isDashboard} />
        <NavBtn to="/workspace" icon="fileText"  label="워크스페이스" active={isWorkspace} />
      </nav>

      {/* 구분선 */}
      <div className="h-5 w-px bg-zinc-200 dark:bg-zinc-700 mx-1" />

      {/* 테마 토글 */}
      <button
        onClick={toggleTheme}
        title="테마 전환"
        className="w-9 h-9 grid place-items-center rounded-lg border border-zinc-200 dark:border-zinc-700 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800"
      >
        <Ic name={theme === 'dark' ? 'sun' : 'moon'} />
      </button>

      {/* 워크스페이스에서만 새 대화 버튼 표시 */}
      {isWorkspace && (
        <button
          onClick={onNewConversation}
          className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-200 dark:border-zinc-700 px-3 py-1.5 text-sm text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800"
        >
          <Ic name="plus" />
          새 대화
        </button>
      )}

      {/* 로그인 / 유저 아바타 + 로그아웃 */}
      {token ? (
        <div className="flex items-center gap-2">
          {/* 이니셜 아바타 */}
          <div className="w-8 h-8 rounded-full bg-blue-600 text-white text-xs font-bold grid place-items-center select-none">
            {user?.name?.charAt(0) ?? '?'}
          </div>
          {/* 로그아웃 */}
          <button
            onClick={handleLogout}
            title="로그아웃"
            className="w-8 h-8 grid place-items-center rounded-lg text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800"
          >
            <Ic name="logout" className="w-4 h-4" />
          </button>
        </div>
      ) : (
        <button
          onClick={() => navigate('/login')}
          className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-200 dark:border-zinc-700 px-3 py-1.5 text-sm text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800"
        >
          로그인
        </button>
      )}
    </header>
  )
}
