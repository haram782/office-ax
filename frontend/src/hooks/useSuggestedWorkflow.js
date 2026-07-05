import { useCallback, useEffect, useState } from 'react'
import { getSuggestedWorkflows } from '../api/client'

// 닫은 제안 id 목록 저장 키 — 같은 제안을 재방문마다 다시 띄우지 않는다
const DISMISSED_KEY = 'ax_dismissed_workflows'

function readDismissed() {
  try {
    return new Set(JSON.parse(localStorage.getItem(DISMISSED_KEY) ?? '[]'))
  } catch {
    return new Set()
  }
}

/**
 * 자동화 제안 워크플로우 조회 훅 (점검 발견 A-3 최소 연결).
 *
 * 백엔드 주간 패턴 감지(detect_weekly_patterns)가 is_suggested로 표시한
 * 워크플로우 중, 아직 활성화되지 않았고 사용자가 닫지 않은 첫 항목을 반환한다.
 *
 * @returns {{ workflow: object|null, dismiss: () => void }}
 */
export function useSuggestedWorkflow() {
  const [workflow, setWorkflow] = useState(null)

  useEffect(() => {
    let cancelled = false
    getSuggestedWorkflows()
      .then((list) => {
        if (cancelled || !Array.isArray(list)) return
        const dismissed = readDismissed()
        const candidate = list.find(
          (w) => w.is_suggested && !w.is_active && !dismissed.has(w.id)
        )
        setWorkflow(candidate ?? null)
      })
      .catch(() => {
        // 제안 조회 실패는 치명적이지 않다 — 배너 없이 조용히 진행
      })
    return () => { cancelled = true }
  }, [])

  const dismiss = useCallback(() => {
    setWorkflow((current) => {
      if (current) {
        const dismissed = readDismissed()
        dismissed.add(current.id)
        localStorage.setItem(DISMISSED_KEY, JSON.stringify([...dismissed]))
      }
      return null
    })
  }, [])

  return { workflow, dismiss }
}
