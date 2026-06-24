import { useNavigate } from 'react-router-dom'
import { Ic } from '../../components/Ic'

/**
 * 자동화 패턴 감지 시 워크스페이스 하단 중앙에 슬라이드 업하는 배너.
 * 파이프라인 빌더로 이동하거나 닫기 가능.
 */
export function AutomationBanner({ onDismiss }) {
  const navigate = useNavigate()

  return (
    // 와이어프레임의 absolute left-1/2 bottom-6 배치
    <div className="absolute left-1/2 bottom-6 z-20 animate-banner-up">
      <div className="flex items-center gap-3 rounded-xl border border-amber-300 dark:border-amber-500/40 bg-amber-50 dark:bg-amber-500/10 shadow-xl px-4 py-3 max-w-[640px]">
        {/* 번개 아이콘 */}
        <div className="w-9 h-9 shrink-0 rounded-lg bg-amber-400/25 grid place-items-center text-amber-600 dark:text-amber-300">
          <Ic name="zap" className="w-5 h-5" />
        </div>

        {/* 텍스트 */}
        <div className="min-w-0">
          <div className="text-sm font-semibold text-amber-800 dark:text-amber-200">
            💡 자동화 패턴 감지!
          </div>
          <div className="text-xs text-amber-700/80 dark:text-amber-300/70">
            동일한 보정 작업이 3회 반복되었습니다. 파이프라인으로 등록할까요?
          </div>
        </div>

        {/* 파이프라인 빌더로 이동 */}
        <button
          onClick={() => { onDismiss(); navigate('/pipeline/new') }}
          className="shrink-0 ml-1 inline-flex items-center gap-1.5 rounded-lg bg-amber-500 hover:bg-amber-600 text-white text-xs font-semibold px-3 py-2"
        >
          파이프라인 빌더로 이동
          <Ic name="arrowRight" className="w-3.5 h-3.5" />
        </button>

        {/* 닫기 */}
        <button
          onClick={onDismiss}
          className="shrink-0 w-7 h-7 grid place-items-center rounded-lg text-amber-600/70 hover:bg-amber-100 dark:hover:bg-amber-500/20"
        >
          <Ic name="x" />
        </button>
      </div>
    </div>
  )
}
