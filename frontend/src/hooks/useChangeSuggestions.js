import { useState, useMemo, useCallback, useEffect } from 'react'
import { deriveChangeSuggestions, buildInitialStatuses } from '../utils/changeSuggestions'
import { patchDocumentChange } from '../api/documentChanges'

export { buildInitialStatuses }

/**
 * 변경 제안 상태 관리 훅 — WorkspaceCenter / PreviewPage 공용.
 *
 * snippetData가 바뀌면 suggestions를 재파생하고,
 * statuses / selectedSuggestionId도 새 목록 기준으로 재초기화한다.
 *
 * suggestion에 changeDbId가 있으면 상태 변경 시 PATCH API를 발화한다.
 * API 실패 시 로컬 상태를 이전 값으로 자동 롤백한다 (낙관적 UI).
 *
 * @param {object|null} snippetData
 * @returns {{
 *   suggestions:            Array,
 *   statuses:               { [id: string]: string },
 *   selectedSuggestionId:   string | null,
 *   setSelectedSuggestionId: (id: string | null) => void,
 *   highlights:             Array,
 *   pendingIds:             Set<string>,
 *   handleSetStatus:        (id: string, next: string) => void,
 *   handleAcceptAll:        () => void,
 *   handleSelectHighlight:  (id: string) => void,
 * }}
 */
export function useChangeSuggestions(snippetData) {
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const suggestions = useMemo(() => deriveChangeSuggestions(snippetData ?? null), [snippetData])

  const [statuses,             setStatuses]             = useState(() => buildInitialStatuses(suggestions))
  const [selectedSuggestionId, setSelectedSuggestionId] = useState(null)
  // API 호출 진행 중인 suggestion id 집합 — 중복 클릭 방지용
  const [pendingIds,           setPendingIds]           = useState(() => new Set())

  // suggestions 참조가 바뀌면 상태를 새 목록 기준으로 재초기화
  useEffect(() => {
    setStatuses(buildInitialStatuses(suggestions))
    setSelectedSuggestionId(prev =>
      prev !== null && suggestions.some(s => s.id === prev) ? prev : null,
    )
  }, [suggestions])

  // highlights = suggestions + 현재 statuses 병합 → resolveViewer에 전달
  const highlights = useMemo(
    () => suggestions.map(s => ({
      ...s,
      status: statuses[s.id] ?? s.status ?? 'pending',
    })),
    [suggestions, statuses],
  )

  /**
   * 개별 상태 변경 — 낙관적 UI + 선택적 API 연동.
   *
   * changeDbId가 없으면 로컬 상태만 변경한다.
   * changeDbId가 있으면 로컬 즉시 반영 후 PATCH API를 발화하고,
   * 실패 시 이전 값으로 롤백한다.
   */
  const handleSetStatus = useCallback((id, nextStatus) => {
    const suggestion = suggestions.find(s => s.id === id)
    const prevStatus = statuses[id] ?? 'pending'

    // 낙관적 업데이트 — API 결과와 무관하게 즉시 반영
    setStatuses(prev => ({ ...prev, [id]: nextStatus }))

    if (!suggestion?.changeDbId) return

    // API 호출 시작 — pendingIds에 추가해 중복 클릭 방지
    setPendingIds(prev => new Set([...prev, id]))

    patchDocumentChange(suggestion.changeDbId, nextStatus)
      .catch(() => {
        // API 실패 → 낙관적 업데이트 롤백
        setStatuses(prev => ({ ...prev, [id]: prevStatus }))
      })
      .finally(() => {
        // 완료(성공·실패) 후 pendingIds에서 제거
        setPendingIds(prev => {
          const updated = new Set(prev)
          updated.delete(id)
          return updated
        })
      })
  }, [suggestions, statuses])

  // 대기 항목 전체 적용 — API 연결은 이번 범위 제외 (개별 건만 연결)
  const handleAcceptAll = useCallback(() => {
    setStatuses(prev => {
      const next = { ...prev }
      for (const s of suggestions) {
        if ((next[s.id] ?? 'pending') === 'pending') next[s.id] = 'applied'
      }
      return next
    })
  }, [suggestions])

  // 뷰어 내부 클릭 → 선택 토글 (같은 항목 재클릭 시 선택 해제)
  const handleSelectHighlight = useCallback((id) => {
    setSelectedSuggestionId(prev => prev === id ? null : id)
  }, [])

  return {
    suggestions,
    statuses,
    selectedSuggestionId,
    setSelectedSuggestionId,
    highlights,
    pendingIds,
    handleSetStatus,
    handleAcceptAll,
    handleSelectHighlight,
  }
}
