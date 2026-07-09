/**
 * 변경 제안 요약 바.
 * 대기/생성 대기/반영/거절 개수, "모두 적용" 버튼, "수정본 생성" 버튼을 제공한다.
 */

// patchStatus → 버튼 렌더 모드 맵
const PATCH_BTN = {
  null:        { label: '수정본 생성',      disabled: false, cls: 'text-blue-600 dark:text-blue-400 border-blue-200 dark:border-blue-700 hover:border-blue-300' },
  generating:  { label: '수정본 생성 중…',  disabled: true,  cls: 'text-zinc-400 border-zinc-200 dark:border-zinc-700' },
  ready:       { label: '수정본 생성됨',    disabled: true,  cls: 'text-emerald-600 dark:text-emerald-400 border-emerald-200 dark:border-emerald-700' },
  failed:      { label: '생성 실패 — 다시 시도', disabled: false, cls: 'text-red-500 border-red-200 dark:border-red-700 hover:border-red-300' },
}

/**
 * @param {{
 *   suggestions:  Array,
 *   statuses:     { [id]: string },
 *   onAcceptAll:    () => void,
 *   isAcceptingAll: boolean,
 *   acceptAllError: string|null,
 *   uploadId:     number|string|null,
 *   versionId:    number|string|null,
 *   patchStatus:  null|'generating'|'ready'|'failed',
 *   onPatch:      (() => void)|null,
 * }} props
 */
export function ChangeSummaryBar({
  suggestions,
  statuses,
  onAcceptAll,
  isAcceptingAll = false,
  acceptAllError = null,
  uploadId    = null,
  versionId   = null,
  patchStatus = null,
  onPatch     = null,
}) {
  // 각 제안의 실효 상태: statuses 맵에 있으면 덮어쓰고 없으면 원본 status 사용
  const statusOf = (s) => statuses[s.id] ?? s.status ?? 'pending'
  const pending    = suggestions.filter(s => statusOf(s) === 'pending').length
  const accepted   = suggestions.filter(s => statusOf(s) === 'accepted').length
  const generating = suggestions.filter(s => statusOf(s) === 'generating').length
  const applied    = suggestions.filter(s => statusOf(s) === 'applied').length
  const failed     = suggestions.filter(s => statusOf(s) === 'failed').length
  const rejected   = suggestions.filter(s => statusOf(s) === 'rejected').length
  const total      = suggestions.length

  // 수정본 생성 버튼 표시 조건 — 생성 대상 항목 + uploadId + versionId 필수
  const selectedForPatch = accepted + generating + applied + failed
  const canShowPatchBtn = selectedForPatch > 0 && uploadId != null && versionId != null && onPatch != null

  const patchBtn = PATCH_BTN[patchStatus] ?? PATCH_BTN.null

  return (
    <div className="flex-shrink-0 flex flex-col gap-0 border-b border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900">
      {/* 상단 행: 제목 + 개수 뱃지 + 모두 적용 */}
      <div className="flex items-center gap-2 px-3 py-2.5">
        {/* 제목 */}
        <span className="text-[11px] font-bold text-zinc-600 dark:text-zinc-300 mr-1">
          수정 제안
        </span>
        <span className="text-[10px] font-semibold text-zinc-400 dark:text-zinc-500">
          {total}건
        </span>

        <div className="flex-1" />

        {/* 개수 뱃지 */}
        <div className="flex items-center gap-1.5">
          {pending > 0 && (
            <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-zinc-100 dark:bg-zinc-800 text-zinc-500 dark:text-zinc-400 tabular-nums">
              대기 {pending}
            </span>
          )}
          {accepted > 0 && (
            <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-blue-50 dark:bg-blue-900/25 text-blue-600 dark:text-blue-400 tabular-nums">
              생성 대기 {accepted}
            </span>
          )}
          {generating > 0 && (
            <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-blue-50 dark:bg-blue-900/25 text-blue-600 dark:text-blue-400 tabular-nums">
              생성 중 {generating}
            </span>
          )}
          {applied > 0 && (
            <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-emerald-50 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400 tabular-nums">
              반영 {applied}
            </span>
          )}
          {failed > 0 && (
            <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-red-50 dark:bg-red-900/20 text-red-500 tabular-nums">
              실패 {failed}
            </span>
          )}
          {rejected > 0 && (
            <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-red-50 dark:bg-red-900/20 text-red-400 tabular-nums">
              거절 {rejected}
            </span>
          )}
        </div>

        {/* 모두 적용 — 대기 항목이 있을 때만 활성, 호출 중에는 비활성화 + 스피너 */}
        {pending > 0 && (
          <button
            onClick={onAcceptAll}
            disabled={isAcceptingAll}
            className="flex-shrink-0 text-[10px] font-medium text-emerald-600 dark:text-emerald-400 hover:text-emerald-700 dark:hover:text-emerald-300 border border-emerald-200 dark:border-emerald-700 hover:border-emerald-300 rounded-md px-2 py-1 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isAcceptingAll && (
              <span className="inline-block w-2.5 h-2.5 border border-current border-t-transparent rounded-full animate-spin mr-1 align-middle" />
            )}
            모두 적용
          </button>
        )}
      </div>

      {/* 전체 적용 실패 시 오류 메시지 */}
      {acceptAllError && (
        <div className="px-3 pb-2 text-[10px] text-red-500">
          {acceptAllError}
        </div>
      )}

      {/* 수정본 생성 버튼 행 — 조건 충족 시만 표시 */}
      {canShowPatchBtn && (
        <div className="px-3 pb-2.5">
          {/* ready 상태는 버튼이 아닌 정적 텍스트로 표시 */}
          {patchStatus === 'ready' ? (
            <div className="text-[10px] font-medium text-emerald-600 dark:text-emerald-400 flex items-center gap-1.5">
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                <path d="M20 6 9 17l-5-5"/>
              </svg>
              수정본 생성됨
            </div>
          ) : (
            <button
              onClick={onPatch}
              disabled={patchBtn.disabled}
              className={`
                w-full text-[10px] font-medium border rounded-md px-2 py-1.5 transition-colors
                disabled:opacity-50 disabled:cursor-not-allowed
                ${patchBtn.cls}
              `}
            >
              {patchStatus === 'generating' && (
                <span className="inline-block w-2.5 h-2.5 border border-current border-t-transparent rounded-full animate-spin mr-1.5 align-middle" />
              )}
              {patchBtn.label}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
