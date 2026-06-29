import { useState, useCallback } from 'react'
import { triggerPatch } from '../api/documentChanges'

/**
 * XLSX patcher 트리거 훅.
 * 버튼 클릭 → API 발화 → 상태 반영까지의 흐름을 캡슐화한다.
 * polling은 이번 범위 제외 — "수정본 생성 요청됨(generating)" 상태만 관리한다.
 *
 * @param {number|string|null} uploadId
 * @param {number|string|null} versionId
 * @returns {{ patchStatus: null|'generating'|'ready'|'failed', trigger: () => void }}
 */
export function usePatchTrigger(uploadId, versionId) {
  // null | 'generating' | 'ready' | 'failed'
  const [patchStatus, setPatchStatus] = useState(null)

  const trigger = useCallback(async () => {
    setPatchStatus('generating')
    try {
      const data = await triggerPatch(uploadId, versionId)
      // BE 응답의 status 값으로 갱신 (통상 'generating')
      setPatchStatus(data.status)
    } catch {
      setPatchStatus('failed')
    }
  }, [uploadId, versionId])

  return { patchStatus, trigger }
}
