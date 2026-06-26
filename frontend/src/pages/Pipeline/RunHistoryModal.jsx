import { Ic } from '../../components/Ic'

/**
 * 파이프라인 실행 기록 모달.
 * 현재는 빈 상태를 표시하며, 추후 실행 기록 API와 연결한다.
 */
export function RunHistoryModal({ pipelineId, onClose }) {
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-zinc-950/50 backdrop-blur-sm">
      <div className="bg-white dark:bg-zinc-900 rounded-2xl border border-zinc-200 dark:border-zinc-800 shadow-2xl w-[520px] max-h-[70vh] flex flex-col fade-in">
        {/* 헤더 */}
        <div className="shrink-0 flex items-center gap-3 px-5 h-14 border-b border-zinc-200 dark:border-zinc-800">
          <Ic name="history" className="w-4 h-4 text-zinc-400" />
          <span className="text-sm font-semibold text-zinc-800 dark:text-zinc-100 flex-1">
            실행 기록
          </span>
          <button
            onClick={onClose}
            className="w-8 h-8 grid place-items-center rounded-lg text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800"
          >
            <Ic name="x" />
          </button>
        </div>

        {/* 본문 — 추후 실행 기록 API 연결 예정 */}
        <div className="flex-1 flex items-center justify-center py-12">
          <div className="text-center">
            <Ic name="history" className="w-8 h-8 text-zinc-200 dark:text-zinc-700 mx-auto mb-3" />
            <p className="text-sm text-zinc-400">아직 실행 기록이 없습니다.</p>
          </div>
        </div>
      </div>
    </div>
  )
}
