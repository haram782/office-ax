import { useState, useCallback, useEffect, useRef } from 'react'
import { triggerPatch } from '../api/documentChanges'

// 서버 폴링 타임아웃과 맞춘 안전장치 — 이 시간이 지나도 generating이면 failed로 전환
const TRIGGER_TIMEOUT_MS = 95_000

/**
 * 패처 트리거 훅.
 * 버튼 클릭 → API 발화 → 상태 반영까지의 흐름을 캡슐화한다.
 * polling은 이번 범위 제외 — "수정본 생성 요청됨(generating)" 상태만 관리한다.
 *
 * TRIGGER_TIMEOUT_MS 이내에 ready/failed로 전환되지 않으면 자동으로 failed로 설정해
 * Celery 태스크 비정상 종료 시 FE 스피너가 무한히 유지되는 것을 방지한다.
 *
 * @param {number|string|null} uploadId
 * @param {number|string|null} versionId
 * @returns {{ patchStatus: null|'generating'|'ready'|'failed', trigger: () => void }}
 */
export function usePatchTrigger(uploadId, versionId) {
  // null | 'generating' | 'ready' | 'failed'
  const [patchStatus, setPatchStatus] = useState(null)
  const timeoutRef = useRef(null)

  useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
    }
  }, [])

  const trigger = useCallback(async () => {
    // 이전 타임아웃 정리
    if (timeoutRef.current) clearTimeout(timeoutRef.current)

    setPatchStatus('generating')

    // 안전장치: 타임아웃 내 완료 안 되면 failed로 강제 전환
    timeoutRef.current = setTimeout(() => {
      setPatchStatus(prev => prev === 'generating' ? 'failed' : prev)
    }, TRIGGER_TIMEOUT_MS)

    try {
      const data = await triggerPatch(uploadId, versionId)
      // BE 응답의 status 값으로 갱신 (통상 'generating')
      setPatchStatus(data.status)
    } catch {
      clearTimeout(timeoutRef.current)
      setPatchStatus('failed')
    }
  }, [uploadId, versionId])

  return { patchStatus, trigger }
}
