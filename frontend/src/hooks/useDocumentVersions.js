import { useState, useEffect } from 'react'
import { fetchDocumentVersions } from '../api/documentChanges'

/**
 * DocumentVersion 목록 조회 훅.
 * 마운트 시 + patchStatus 변경 시 재조회한다.
 *
 * @param {number|string|null} uploadId
 * @param {string|null}        patchStatus - 변경 시 재조회 트리거 (예: 'ready')
 * @returns {{ versions: Array, isLoading: boolean }}
 */
export function useDocumentVersions(uploadId, patchStatus = null) {
  const [versions, setVersions]   = useState([])
  const [isLoading, setIsLoading] = useState(false)

  useEffect(() => {
    // uploadId 없으면 조회하지 않는다
    if (!uploadId) return

    let cancelled = false
    setIsLoading(true)

    fetchDocumentVersions(uploadId)
      .then(data => {
        if (!cancelled) setVersions(data)
      })
      .catch(() => {
        // 인프라 오류 — 빈 목록 유지, 상위에 전파하지 않는다
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false)
      })

    return () => { cancelled = true }
  // patchStatus가 바뀔 때마다 재조회 (generating → ready 전환 감지)
  }, [uploadId, patchStatus])

  return { versions, isLoading }
}
