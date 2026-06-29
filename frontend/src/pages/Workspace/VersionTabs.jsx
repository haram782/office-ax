/**
 * 버전 탭 — 정적 플레이스홀더.
 * 클릭 동작 및 API 연동은 다음 작업으로 미룬다.
 * ViewerShell의 headerExtra 슬롯에 삽입된다.
 */

// 버전 탭 스타일 상수
const TAB_BASE    = 'text-[10px] font-medium px-2 py-0.5 rounded-md border transition-colors cursor-pointer'
const TAB_ACTIVE  = 'bg-zinc-100 dark:bg-zinc-800 border-zinc-300 dark:border-zinc-600 text-zinc-700 dark:text-zinc-200'
const TAB_IDLE    = 'border-transparent text-zinc-400 dark:text-zinc-500 hover:text-zinc-600 dark:hover:text-zinc-300'

/**
 * @param {{ versions: Array }} props - 현재는 미사용. 다음 작업에서 실제 버전 목록으로 교체
 */
export function VersionTabs({ versions = [] }) {
  // versions가 없으면 플레이스홀더 탭만 표시
  const hasVersions = versions.length > 0

  return (
    <div className="flex items-center gap-0.5 flex-shrink-0">
      {/* 원본 탭 — 항상 표시 */}
      <button className={`${TAB_BASE} ${TAB_ACTIVE}`}>
        원본
      </button>

      {/* 실제 버전 탭 또는 플레이스홀더 */}
      {hasVersions ? (
        versions.map((v, i) => (
          <button key={v.id ?? i} className={`${TAB_BASE} ${TAB_IDLE}`}>
            v{i + 1}
          </button>
        ))
      ) : (
        // 플레이스홀더 — BE 연동 전 자리만 확보
        <button disabled className={`${TAB_BASE} opacity-30 border-dashed border-zinc-300 dark:border-zinc-600 text-zinc-400 cursor-default`}>
          v1
        </button>
      )}

      {/* 새 버전 생성 버튼 — 클릭 동작은 다음 작업 */}
      <button disabled className={`${TAB_BASE} opacity-40 text-zinc-400 border-zinc-200 dark:border-zinc-700 cursor-default`}>
        + 새 버전
      </button>
    </div>
  )
}
