import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useGoogleLogin } from '@react-oauth/google'
import { Ic } from '../../components/Ic'
import { useTheme } from '../../theme'
import { googleLogin } from '../../api/client'

/** Google 공식 4색 로고 */
function GoogleLogo() {
  return (
    <svg viewBox="0 0 24 24" className="w-5 h-5 shrink-0">
      <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
      <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
      <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z" fill="#FBBC05"/>
      <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
    </svg>
  )
}

/**
 * 로그인 페이지.
 * mode: 'default' | 'loading' | 'error'
 */
export default function Login() {
  const navigate = useNavigate()
  const { theme, toggleTheme } = useTheme()
  const [mode, setMode] = useState('default')

  const login = useGoogleLogin({
    onSuccess: async (tokenResponse) => {
      try {
        const data = await googleLogin(tokenResponse.access_token)
        localStorage.setItem('auth_token', data.token)
        localStorage.setItem('ax_user', JSON.stringify(data.user))
        navigate('/', { replace: true })
      } catch {
        setMode('error')
      }
    },
    onError: () => setMode('error'),
  })

  const handleGoogleClick = () => {
    setMode('loading')
    login()
  }

  return (
    <div className="relative min-h-screen flex flex-col items-center justify-center bg-zinc-50 dark:bg-zinc-950 px-4">
      {/* 테마 토글 */}
      <button
        onClick={toggleTheme}
        className="fixed top-4 right-4 w-9 h-9 rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 hover:bg-zinc-100 dark:hover:bg-zinc-700 grid place-items-center text-zinc-600 dark:text-zinc-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-zinc-950"
      >
        <Ic name={theme === 'dark' ? 'sun' : 'moon'} className="w-4 h-4" />
      </button>

      {/* 로그인 카드 */}
      <div
        className="max-w-[400px] w-full rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-10 fade-in"
        style={{ boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}
      >
        {/* 로고 블록 */}
        <div className="flex flex-col items-center mb-6">
          <div className="w-10 h-10 rounded-xl bg-blue-600 text-white grid place-items-center font-bold text-sm mb-3">
            AX
          </div>
          <div className="font-bold text-zinc-800 dark:text-zinc-100 text-xl">Office-AX</div>
        </div>

        {/* 부제 */}
        <p className="text-sm text-zinc-400 text-center mb-8">
          AI 문서 자동화 · 오류 검출 · 어투 일괄 변환
        </p>

        {/* 구분선 */}
        <div className="h-px bg-zinc-100 dark:bg-zinc-800 mb-8" />

        {/* 에러 배너 */}
        {mode === 'error' && (
          <div className="mb-4 rounded-xl border border-rose-200 dark:border-rose-500/30 bg-rose-50 dark:bg-rose-500/10 px-4 py-3 flex items-center gap-2.5">
            <span className="text-rose-500 shrink-0"><Ic name="alert" className="w-4 h-4" /></span>
            <span className="flex-1 text-sm text-rose-700 dark:text-rose-300">
              인증에 실패했습니다. 다시 시도해주세요.
            </span>
            <button
              onClick={() => setMode('default')}
              className="shrink-0 w-6 h-6 grid place-items-center rounded-md text-rose-400 hover:bg-rose-100 dark:hover:bg-rose-500/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-400"
            >
              <Ic name="x" className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* Google 버튼 */}
        {mode === 'loading' ? (
          <button
            disabled
            className="w-full h-11 rounded-xl flex items-center justify-center gap-2.5 text-sm font-medium border border-zinc-200 dark:border-zinc-700 bg-zinc-100 dark:bg-zinc-800 cursor-not-allowed focus-visible:outline-none"
          >
            <span className="w-4 h-4 border-2 border-zinc-300 dark:border-zinc-600 border-t-blue-600 rounded-full animate-spin" />
            <span className="text-zinc-500 dark:text-zinc-400">Google 인증 중...</span>
          </button>
        ) : (
          <button
            onClick={handleGoogleClick}
            className="w-full h-11 rounded-xl flex items-center justify-center gap-2.5 text-sm font-medium border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 hover:bg-zinc-50 dark:hover:bg-zinc-700 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-zinc-900"
          >
            <GoogleLogo />
            <span className="text-zinc-700 dark:text-zinc-200">
              {mode === 'error' ? '다시 시도하기' : 'Google 계정으로 시작하기'}
            </span>
          </button>
        )}

        {/* 캡션 */}
        <p className="mt-4 text-xs text-zinc-400 text-center leading-relaxed">
          {mode === 'loading'
            ? 'Google 인증 팝업이 열렸습니다. 잠시만 기다려주세요.'
            : '로그인 또는 회원가입 — Google 계정으로 자동 생성됩니다'}
        </p>

        {/* 테스트 모드 구분선 */}
        <div className="flex items-center gap-3 mt-6">
          <div className="flex-1 h-px bg-zinc-100 dark:bg-zinc-800" />
          <span className="text-[11px] text-zinc-400 shrink-0">테스트 모드</span>
          <div className="flex-1 h-px bg-zinc-100 dark:bg-zinc-800" />
        </div>

        {/* 게스트 계정 버튼 2개 */}
        <div className="flex gap-2 mt-3">
          {[
            { label: '게스트1', token: 'guest-token-1', name: '게스트1', email: 'guest1@test.com' },
            { label: '게스트2', token: 'guest-token-2', name: '게스트2', email: 'guest2@test.com' },
          ].map(g => (
            <button
              key={g.label}
              onClick={() => {
                localStorage.setItem('auth_token', g.token)
                localStorage.setItem('ax_user', JSON.stringify({ name: g.name, email: g.email }))
                navigate('/workspace', { replace: true })
              }}
              className="flex-1 h-9 rounded-xl border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800/60 hover:bg-zinc-100 dark:hover:bg-zinc-800 text-xs text-zinc-500 dark:text-zinc-400 transition-colors"
            >
              {g.label}로 시작
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
