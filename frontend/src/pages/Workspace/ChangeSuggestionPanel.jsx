import { useCallback } from 'react'
import { ChangeSummaryBar }    from './ChangeSummaryBar'
import { ChangeSuggestionCard } from './ChangeSuggestionCard'

/**
 * 변경 제안 패널.
 * statuses 상태는 WorkspaceCenter에서 관리하며 props로 받는다.
 * (statuses를 상위로 lift해서 resolveViewer(highlights)와 공유한다)
 *
 * @param {{
 *   suggestions:          Array,
 *   statuses:             { [id]: 'pending' | 'accepted' | 'generating' | 'applied' | 'failed' | 'rejected' },
 *   pendingIds:           Set<string>,
 *   onSetStatus:          (id: string, next: string) => void,
 *   onAcceptAll:          () => void,
 *   isAcceptingAll:       boolean,
 *   acceptAllError:       string|null,
 *   autoRejectedIds:      Set<string>,
 *   selectedSuggestionId: string | null,
 *   onSelectSuggestion:   (id: string | null) => void,
 *   uploadId:             number|string|null,
 *   versionId:            number|string|null,
 *   patchStatus:          null|'generating'|'ready'|'failed',
 *   onPatch:              (() => void)|null,
 *   canEditStatuses:      boolean,
 * }} props
 */
export function ChangeSuggestionPanel({
  suggestions,
  statuses,
  pendingIds      = new Set(),
  onSetStatus,
  onAcceptAll,
  isAcceptingAll  = false,
  acceptAllError  = null,
  autoRejectedIds = new Set(),
  selectedSuggestionId,
  onSelectSuggestion,
  uploadId     = null,
  versionId    = null,
  patchStatus  = null,
  onPatch      = null,
  canEditStatuses = true,
}) {
  const handleSelect = useCallback((id) => {
    // 같은 카드 재클릭 시 선택 해제
    onSelectSuggestion(selectedSuggestionId === id ? null : id)
  }, [onSelectSuggestion, selectedSuggestionId])

  return (
    <div className="w-72 flex-shrink-0 flex flex-col border-l border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-950 min-h-0">
      {/* 요약 바 — 수정본 생성 버튼 포함 */}
      <ChangeSummaryBar
        suggestions={suggestions}
        statuses={statuses}
        onAcceptAll={onAcceptAll}
        isAcceptingAll={isAcceptingAll}
        acceptAllError={acceptAllError}
        uploadId={uploadId}
        versionId={versionId}
        patchStatus={patchStatus}
        onPatch={onPatch}
      />

      {/* 카드 목록 */}
      <div className="flex-1 overflow-y-auto p-2.5 space-y-2">
        {suggestions.length === 0 ? (
          // 빈 상태 — suggestion이 0건일 때
          <div className="flex flex-col items-center justify-center h-full gap-2 text-zinc-400 py-10">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
              <path d="M20 6 9 17l-5-5"/>
            </svg>
            <p className="text-xs text-center leading-relaxed">수정 제안 없음</p>
          </div>
        ) : (
          suggestions.map(s => (
            <ChangeSuggestionCard
              key={s.id}
              suggestion={s}
              status={statuses[s.id] ?? 'pending'}
              isSelected={selectedSuggestionId === s.id}
              isPending={pendingIds.has(s.id)}
              isAutoRejected={autoRejectedIds.has(s.id)}
              canEdit={canEditStatuses}
              canReset={canEditStatuses}
              onSelect={() => handleSelect(s.id)}
              onAccept={() => onSetStatus(s.id, 'applied')}
              onReject={() => onSetStatus(s.id, 'rejected')}
              onReset={() => onSetStatus(s.id, 'pending')}
            />
          ))
        )}
      </div>
    </div>
  )
}
