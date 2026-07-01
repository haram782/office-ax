import { useState, useMemo, useCallback, useEffect } from 'react'
import { deriveChangeSuggestions, buildInitialStatuses } from '../utils/changeSuggestions'
import { patchDocumentChange, acceptAllChanges } from '../api/documentChanges'

export { buildInitialStatuses }

// 서버가 reason에 덧붙이는 자동 반려 표식 — confidence 충돌 자동 해소 결과 판별용
const AUTO_REJECT_MARK = /\[자동 반려:/

/**
 * 변경 제안 상태 관리 훅 — WorkspaceCenter / PreviewPage 공용.
 *
 * snippetData가 바뀌면 suggestions를 재파생하고,
 * statuses / selectedSuggestionId도 새 목록 기준으로 재초기화한다.
 *
 * suggestion에 changeDbId가 있으면 상태 변경 시 PATCH API를 발화한다.
 * API 실패 시 로컬 상태를 이전 값으로 자동 롤백한다 (낙관적 UI).
 *
 * @param {object|null}         snippetData
 * @param {number|string|null} [uploadId]  - 전체 적용 서버 연동에 필요 (없으면 로컬 폴백)
 * @param {number|string|null} [versionId] - 전체 적용 서버 연동에 필요 (없으면 로컬 폴백)
 * @returns {{
 *   suggestions:            Array,
 *   statuses:               { [id: string]: string },
 *   selectedSuggestionId:   string | null,
 *   setSelectedSuggestionId: (id: string | null) => void,
 *   highlights:             Array,
 *   pendingIds:             Set<string>,
 *   isAcceptingAll:         boolean,
 *   acceptAllError:         string | null,
 *   autoRejectedIds:        Set<string>,
 *   handleSetStatus:        (id: string, next: string) => void,
 *   handleAcceptAll:        () => void,
 *   handleSelectHighlight:  (id: string) => void,
 * }}
 */
export function useChangeSuggestions(snippetData, uploadId = null, versionId = null) {
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const suggestions = useMemo(() => deriveChangeSuggestions(snippetData ?? null), [snippetData])

  const [statuses,             setStatuses]             = useState(() => buildInitialStatuses(suggestions))
  const [selectedSuggestionId, setSelectedSuggestionId] = useState(null)
  // API 호출 진행 중인 suggestion id 집합 — 중복 클릭 방지용
  const [pendingIds,           setPendingIds]           = useState(() => new Set())
  // 전체 적용 API 호출 진행 상태 — 중복 클릭 방지용
  const [isAcceptingAll,       setIsAcceptingAll]       = useState(false)
  const [acceptAllError,       setAcceptAllError]       = useState(null)
  // 서버가 confidence 충돌로 자동 반려한 suggestion id 집합 — 배지 표시용
  const [autoRejectedIds,      setAutoRejectedIds]      = useState(() => new Set())

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
      .catch((err) => {
        // 'applied' 전환 시 400: DB가 이미 'applied' 상태(applied→applied 전환 불가) — 낙관적 업데이트 유지
        // 그 외 오류는 낙관적 업데이트를 롤백해 데이터 정합성을 보장한다
        const dbAlreadyApplied = nextStatus === 'applied' && err?.response?.status === 400
        if (!dbAlreadyApplied) {
          setStatuses(prev => ({ ...prev, [id]: prevStatus }))
        }
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

  /**
   * 대기 항목 전체 적용.
   *
   * uploadId·versionId가 없으면 로컬 상태만 변경한다 (기존 동작 유지).
   * 있으면 서버에 위임한다 — 충돌 해소 결과를 미리 알 수 없으므로
   * 낙관적 업데이트 없이, 응답을 받은 뒤에만 statuses를 반영한다.
   */
  const handleAcceptAll = useCallback(async () => {
    if (!uploadId || !versionId) {
      setStatuses(prev => {
        const next = { ...prev }
        for (const s of suggestions) {
          if ((next[s.id] ?? 'pending') === 'pending') next[s.id] = 'applied'
        }
        return next
      })
      return
    }

    if (isAcceptingAll) return

    setIsAcceptingAll(true)
    setAcceptAllError(null)

    try {
      const { applied = [], rejected = [] } = await acceptAllChanges(uploadId, versionId)

      setStatuses(prev => {
        const next = { ...prev }
        for (const item of applied) {
          const suggestion = suggestions.find(s => s.changeDbId === item.id)
          if (suggestion) next[suggestion.id] = 'applied'
        }
        for (const item of rejected) {
          const suggestion = suggestions.find(s => s.changeDbId === item.id)
          if (suggestion) next[suggestion.id] = 'rejected'
        }
        return next
      })

      setAutoRejectedIds(() => {
        const next = new Set()
        for (const item of rejected) {
          if (!AUTO_REJECT_MARK.test(item.reason ?? '')) continue
          const suggestion = suggestions.find(s => s.changeDbId === item.id)
          if (suggestion) next.add(suggestion.id)
        }
        return next
      })
    } catch {
      // 실패 시 로컬 상태는 변경하지 않는다 (낙관적 업데이트를 하지 않았으므로 롤백도 불필요)
      setAcceptAllError('전체 적용 중 오류가 발생했습니다.')
    } finally {
      setIsAcceptingAll(false)
    }
  }, [suggestions, uploadId, versionId, isAcceptingAll])

  // 뷰어 내부 클릭 → 선택 토글 (같은 항목 재클릭 시 선택 해제)
  const handleSelectHighlight = useCallback((id) => {
    setSelectedSuggestionId(prev => prev === id ? null : id)
  }, [])

  return {
    suggestions,
    statuses,
    setStatuses,
    selectedSuggestionId,
    setSelectedSuggestionId,
    highlights,
    pendingIds,
    isAcceptingAll,
    acceptAllError,
    autoRejectedIds,
    handleSetStatus,
    handleAcceptAll,
    handleSelectHighlight,
  }
}
