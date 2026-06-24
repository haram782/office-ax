import { useNavigate, useParams } from 'react-router-dom'
import { Ic }            from '../../components/Ic'
import { useTheme }      from '../../theme'
import { PipelineFlow }  from './PipelineFlow'

/**
 * 파이프라인 빌더 페이지.
 * Topbar를 공유하지 않고 독자적인 헤더를 가진다.
 * 노드 캔버스는 격자 배경 위에 PipelineFlow를 렌더한다.
 */
export default function Pipeline() {
  const navigate    = useNavigate()
  const { id }      = useParams()
  const { theme, toggleTheme } = useTheme()

  // 격자 배경 패턴 (다크 모드 대응)
  const gridColor = theme === 'dark' ? 'rgba(120,120,128,.10)' : 'rgba(120,120,128,.13)'
  const gridStyle = {
    backgroundImage: `linear-gradient(${gridColor} 1px,transparent 1px),linear-gradient(90deg,${gridColor} 1px,transparent 1px)`,
    backgroundSize: '28px 28px',
  }

  return (
    <div className="h-screen flex flex-col bg-zinc-100 dark:bg-zinc-950">
      {/* 파이프라인 전용 헤더 */}
      <header className="h-14 shrink-0 flex items-center gap-3 px-4 border-b border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900">
        {/* 대시보드로 복귀 */}
        <button
          onClick={() => navigate('/')}
          className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-200 dark:border-zinc-700 px-3 py-1.5 text-sm text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800"
        >
          <Ic name="arrowLeft" />
          대시보드로 돌아가기
        </button>

        <div className="h-5 w-px bg-zinc-200 dark:bg-zinc-700" />

        {/* 파이프라인 이름 (편집 가능) */}
        <div className="flex items-center gap-2">
          <Ic name="workflow" className="w-4 h-4 text-blue-600" />
          <input
            defaultValue={id === 'new' ? '새 파이프라인' : '청약서 자동 검토 및 보정'}
            className="text-sm font-semibold text-zinc-800 dark:text-zinc-100 bg-transparent outline-none border-b border-transparent focus:border-blue-400 w-52"
          />
        </div>

        {/* 파이프라인 타입 배지 */}
        <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300">
          타입 C · 스케줄링형
        </span>

        <div className="flex-1" />

        {/* 테마 토글 */}
        <button
          onClick={toggleTheme}
          className="w-9 h-9 grid place-items-center rounded-lg border border-zinc-200 dark:border-zinc-700 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800"
        >
          <Ic name={theme === 'dark' ? 'sun' : 'moon'} />
        </button>

        {/* 실행 기록 */}
        <button className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-200 dark:border-zinc-700 px-3 py-1.5 text-sm text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800">
          <Ic name="history" />
          실행 기록
        </button>

        {/* 저장 */}
        <button className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium px-3.5 py-1.5">
          <Ic name="save" />
          파이프라인 저장
        </button>
      </header>

      {/* 노드 캔버스 */}
      <div className="flex-1 overflow-auto" style={gridStyle}>
        <div className="min-w-max min-h-full flex flex-col justify-center px-20 py-16">
          <div className="mb-8">
            <div className="text-xs font-semibold text-zinc-400 uppercase tracking-wide mb-1">비주얼 워크플로우</div>
            <div className="text-sm text-zinc-500 dark:text-zinc-400">
              트리거부터 결과까지 4개 노드가 연결되어 있습니다.
            </div>
          </div>
          <PipelineFlow />
        </div>
      </div>
    </div>
  )
}
