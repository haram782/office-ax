/**
 * 버전 탭 — DocumentVersion 배열을 받아 탭으로 렌더한다.
 * ViewerShell의 versionPanel 슬롯에 삽입된다.
 */

// 탭 공통 기본 스타일
const TAB_BASE   = 'min-w-[118px] max-w-[168px] text-left px-2.5 py-1.5 border-b-2 transition-colors'
const TAB_ACTIVE = 'bg-white dark:bg-zinc-900 border-blue-500 text-zinc-800 dark:text-zinc-100'
const TAB_IDLE   = 'border-transparent text-zinc-500 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800/70 hover:text-zinc-700 dark:hover:text-zinc-200'
const TAB_OFF    = 'border-transparent text-zinc-300 dark:text-zinc-600 cursor-not-allowed opacity-70'

const STATUS_LABELS = {
  original:   '원본',
  draft:      '초안',
  generating: '생성 중',
  ready:      '완료',
  failed:     '실패',
  needs_confirmation: '위치 확인 필요',
}

/**
 * 버전 상태에 따른 레이블 텍스트 반환.
 * original은 항상 "원본", 나머지는 label 또는 "v{version_number}"
 */
function versionLabel(v) {
  if (v.status === 'original') return '원본'
  return v.label || `v${v.version_number}`
}

function formatVersionTime(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const pad = (n) => String(n).padStart(2, '0')
  return `${pad(date.getMonth() + 1)}.${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function versionMeta(v) {
  const parts = []
  if (v.version_number) parts.push(`v${v.version_number}`)
  const time = formatVersionTime(v.updated_at || v.created_at)
  if (time) parts.push(time)
  return parts.join(' · ')
}

/**
 * @param {{
 *   versions:          Array<{ id, version_number, status, label, created_at, updated_at }>,
 *   selectedVersionId: number | null,
 *   onSelectVersion:   (version: object) => void,
 *   fallbackFailureMessage?: string,
 *   fallbackFailureCode?: string,
 * }} props
 */
export function VersionTabs({
  versions = [],
  selectedVersionId = null,
  onSelectVersion,
  fallbackFailureMessage = '',
  fallbackFailureCode = '',
}) {
  // 버전 배열이 없으면 원본 탭 플레이스홀더만 표시
  if (versions.length === 0) {
    return (
      <div className="shrink-0 border-b border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-950 px-3">
        <button className={`${TAB_BASE} ${TAB_ACTIVE}`} data-active="true">
          <span className="block text-[11px] font-semibold">원본</span>
          <span className="block text-[10px] text-zinc-400">v1</span>
        </button>
      </div>
    )
  }

  return (
    <div className="shrink-0 border-b border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-950">
      <div className="flex items-stretch gap-0 overflow-x-auto px-3">
        {versions.map((v) => {
          const isActive      = v.id === selectedVersionId
          const isGenerating  = v.status === 'generating'
          const isFailed      = v.status === 'failed'
          const isDisabled    = isGenerating
          const label         = versionLabel(v)
          const statusLabel   = STATUS_LABELS[v.status] || v.status
          const meta          = versionMeta(v)

          return (
            <button
              key={v.id}
              disabled={isDisabled}
              data-active={isActive ? 'true' : 'false'}
              onClick={() => !isDisabled && onSelectVersion?.(v)}
              className={`${TAB_BASE} ${isActive ? TAB_ACTIVE : isDisabled ? TAB_OFF : TAB_IDLE}`}
            >
              <span className="flex items-center justify-between gap-1">
                <span className="min-w-0 truncate text-[11px] font-semibold">{label}</span>
                <span className="shrink-0 text-[9px] font-medium text-zinc-400 dark:text-zinc-500">
                  {isGenerating && (
                    <span className="inline-block w-2 h-2 border border-current border-t-transparent rounded-full animate-spin mr-1 align-middle" />
                  )}
                  {isFailed && <span className="mr-1 text-red-400">!</span>}
                  {statusLabel}
                </span>
              </span>
              {meta && (
                <span className="mt-0.5 block truncate text-[10px] font-normal text-zinc-400 dark:text-zinc-500">
                  {meta}
                </span>
              )}
            </button>
          )
        })}
      </div>
      {fallbackFailureMessage && (
        <p
          role={fallbackFailureCode === 'ambiguous_anchor' ? 'status' : 'alert'}
          className={`mx-3 mb-2 rounded px-2.5 py-2 text-[11px] leading-relaxed ${
            fallbackFailureCode === 'ambiguous_anchor'
              ? 'bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300'
              : 'bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-300'
          }`}
        >
          {fallbackFailureMessage}
        </p>
      )}
    </div>
  )
}
