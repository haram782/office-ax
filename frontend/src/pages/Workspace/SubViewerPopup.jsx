import { Ic } from '../../components/Ic'
import { resolveViewer } from '../../components/DocumentPanel'

/**
 * 워크스페이스 내 서브 뷰어 팝업 (인페이지 모달).
 * 메인 뷰어와 동기화 상태를 표시하며, 메인 뷰어와 동일한 resolveViewer()를 사용한다.
 */
export function SubViewerPopup({ previewData, isFixed, onClose, onReplayHighlight }) {
  const { filename, artifactUrl } = previewData

  return (
    // 모달 오버레이
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/40 backdrop-blur-sm animate-fade-in"
      onClick={onClose}
    >
      <div
        onClick={e => e.stopPropagation()}
        className="w-[560px] max-h-[80vh] flex flex-col rounded-xl bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 shadow-2xl overflow-hidden"
      >
        {/* 팝업 헤더 */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-200 dark:border-zinc-800">
          <div className="flex items-center gap-2 text-sm font-medium text-zinc-700 dark:text-zinc-200">
            <Ic name="externalLink" className="w-4 h-4 text-blue-600" />
            서브 뷰어 · {filename}
          </div>
          <div className="flex items-center gap-2">
            {/* 동기화 상태 인디케이터 */}
            <span className="inline-flex items-center gap-1.5 text-[11px] text-emerald-600 dark:text-emerald-400">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
              메인 뷰어와 동기화
            </span>
            <button
              onClick={onClose}
              className="w-7 h-7 grid place-items-center rounded-lg text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800"
            >
              <Ic name="x" />
            </button>
          </div>
        </div>

        {/* 뷰어 본문 */}
        <div className="flex-1 overflow-auto bg-zinc-100 dark:bg-zinc-950 flex justify-center items-start min-h-0">
          {resolveViewer(previewData)}
        </div>

        {/* 팝업 푸터 */}
        <div className="px-4 py-2.5 border-t border-zinc-200 dark:border-zinc-800 flex items-center justify-between text-xs text-zinc-400">
          <span>{isFixed ? '하이라이트 1건 · 동기화됨' : '변경 사항 없음'}</span>
          {onReplayHighlight && (
            <button
              onClick={onReplayHighlight}
              className="inline-flex items-center gap-1 text-blue-600 dark:text-blue-400 hover:underline"
            >
              <Ic name="history" className="w-3.5 h-3.5" />
              하이라이트 재생
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
