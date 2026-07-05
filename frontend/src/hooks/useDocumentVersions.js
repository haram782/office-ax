import { useState, useEffect } from 'react'
import { fetchDocumentVersions } from '../api/documentChanges'

// polling 간격 — 너무 잦은 재조회로 서버 부하를 주지 않을 정도의 간격
const POLL_INTERVAL_MS = 3000
// polling 최대 지속 시간 — 서버 무응답 등 비정상 상황에서 무한 polling 방지
const POLL_TIMEOUT_MS = 90000

// 응답에 generating 상태 버전이 하나라도 남아있는지 확인
function hasGeneratingVersion(list) {
  return Array.isArray(list) && list.some(v => v.status === 'generating')
}

/**
 * DocumentVersion 목록 조회 훅.
 * 마운트 시 + patchStatus 변경 시 재조회한다.
 *
 * 조회 결과에 status === 'generating'인 버전이 있으면 3초 간격으로
 * 자동 재조회(polling)한다. 모든 버전이 ready/failed로 전환되거나
 * polling 시작 후 90초가 지나면 자동으로 중단한다.
 *
 * @param {number|string|null} uploadId
 * @param {string|null}        patchStatus - 변경 시 재조회 트리거 (예: 'ready')
 * @param {number|string|null} refreshKey  - 변경 시 재조회 트리거 (예: 채팅발 draft version_id)
 * @returns {{ versions: Array, isLoading: boolean }}
 */
export function useDocumentVersions(uploadId, patchStatus = null, refreshKey = null) {
  const [versions, setVersions]   = useState([])
  const [isLoading, setIsLoading] = useState(false)

  useEffect(() => {
    // uploadId 없으면 조회하지 않는다
    if (!uploadId) return

    let cancelled = false
    let timeoutId = null
    const pollStartedAt = Date.now()

    // isInitial: 최초 마운트/deps 변경 조회 여부 — isLoading 표시 대상 구분용
    const fetchAndSchedule = (isInitial) => {
      if (isInitial) setIsLoading(true)

      fetchDocumentVersions(uploadId)
        .then(data => {
          if (cancelled) return
          setVersions(data)

          if (!hasGeneratingVersion(data)) return

          // 타임아웃 내에서만 다음 polling을 예약한다
          const elapsed = Date.now() - pollStartedAt
          if (elapsed < POLL_TIMEOUT_MS) {
            timeoutId = setTimeout(() => fetchAndSchedule(false), POLL_INTERVAL_MS)
          }
        })
        .catch(() => {
          // 인프라 오류 — 빈 목록 유지, 상위에 전파하지 않는다
        })
        .finally(() => {
          if (isInitial && !cancelled) setIsLoading(false)
        })
    }

    fetchAndSchedule(true)

    // uploadId 변경 또는 unmount 시 진행 중인 polling 타이머를 정리한다
    return () => {
      cancelled = true
      if (timeoutId) clearTimeout(timeoutId)
    }
  // patchStatus 변경(generating → ready 전환)과 refreshKey 변경(채팅에서 새 draft
  // 버전 생성) 모두 재조회 트리거다 — 채팅발 버전이 탭에 즉시 반영되게 한다
  }, [uploadId, patchStatus, refreshKey])

  return { versions, isLoading }
}
