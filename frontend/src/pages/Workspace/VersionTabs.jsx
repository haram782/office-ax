/**
 * 버전 탭 — DocumentVersion 배열을 받아 탭으로 렌더한다.
 * ViewerShell의 headerExtra 슬롯에 삽입된다.
 */

// 탭 공통 기본 스타일
const TAB_BASE   = 'text-[10px] font-medium px-2 py-0.5 rounded-md border transition-colors'
const TAB_ACTIVE = 'bg-zinc-100 dark:bg-zinc-800 border-zinc-300 dark:border-zinc-600 text-zinc-700 dark:text-zinc-200'
const TAB_IDLE   = 'border-transparent text-zinc-400 dark:text-zinc-500 hover:text-zinc-600 dark:hover:text-zinc-300 hover:border-zinc-200 dark:hover:border-zinc-700'
const TAB_OFF    = 'border-transparent text-zinc-300 dark:text-zinc-600 cursor-not-allowed opacity-60'

/**
 * 버전 상태에 따른 레이블 텍스트 반환.
 * original은 항상 "원본", 나머지는 label 또는 "v{version_number}"
 */
function versionLabel(v) {
  if (v.status === 'original') return '원본'
  return v.label || `v${v.version_number}`
}

/**
 * @param {{
 *   versions:          Array<{ id, version_number, status, label }>,
 *   selectedVersionId: number | null,
 *   onSelectVersion:   (version: object) => void,
 * }} props
 */
export function VersionTabs({ versions = [], selectedVersionId = null, onSelectVersion }) {
  // 버전 배열이 없으면 원본 탭 플레이스홀더만 표시
  if (versions.length === 0) {
    return (
      <div className="flex items-center gap-0.5 flex-shrink-0">
        <button className={`${TAB_BASE} ${TAB_ACTIVE}`} data-active="true">
          원본
        </button>
      </div>
    )
  }

  return (
    <div className="flex items-center gap-0.5 flex-shrink-0">
      {versions.map((v) => {
        const isActive      = v.id === selectedVersionId
        const isGenerating  = v.status === 'generating'
        const isFailed      = v.status === 'failed'
        const isDisabled    = isGenerating || isFailed
        const label         = versionLabel(v)

        return (
          <button
            key={v.id}
            disabled={isDisabled}
            data-active={isActive ? 'true' : 'false'}
            onClick={() => !isDisabled && onSelectVersion?.(v)}
            className={`${TAB_BASE} ${isActive ? TAB_ACTIVE : isDisabled ? TAB_OFF : TAB_IDLE}`}
          >
            {/* generating 탭에 스피너 표시 */}
            {isGenerating && (
              <span className="inline-block w-2 h-2 border border-current border-t-transparent rounded-full animate-spin mr-1 align-middle" />
            )}
            {/* failed 탭에 오류 아이콘 표시 */}
            {isFailed && (
              <span className="mr-1 text-red-400">!</span>
            )}
            {label}
          </button>
        )
      })}
    </div>
  )
}
