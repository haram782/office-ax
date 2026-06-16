import { useState, useCallback, useRef, useEffect } from 'react'
import { uploadFile, getUploadResult, getSuggestedWorkflows } from '../api/client'

const POLL_INTERVAL_MS = 2500
const MAX_POLLS = 40   // 100초 대기 후 타임아웃

/**
 * 문서 분석 전체 흐름을 관리하는 상태 머신 훅.
 *
 * phase 전이: idle → uploading → analyzing → done | error
 *
 * 외부 상태 관리 라이브러리 없이 useRef 기반 인터벌 + useState로만 구성.
 * 컴포넌트 언마운트 시 인터벌이 자동으로 정리된다.
 */
export function useDocumentAnalysis() {
  const [phase, setPhase] = useState('idle')
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [suggestedWorkflow, setSuggestedWorkflow] = useState(null)

  const intervalRef = useRef(null)
  const pollCountRef = useRef(0)

  const stopPolling = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
  }, [])

  // 언마운트 시 진행 중인 폴링 정리
  useEffect(() => () => stopPolling(), [stopPolling])

  const analyze = useCallback(async (file) => {
    stopPolling()
    setPhase('uploading')
    setResult(null)
    setError(null)
    setSuggestedWorkflow(null)
    pollCountRef.current = 0

    let uploadId
    try {
      const res = await uploadFile(file)
      uploadId = res.upload_id
    } catch (err) {
      setPhase('error')
      setError(err?.response?.data?.error ?? '파일 업로드에 실패했습니다.')
      return
    }

    setPhase('analyzing')

    intervalRef.current = setInterval(async () => {
      pollCountRef.current += 1

      if (pollCountRef.current > MAX_POLLS) {
        stopPolling()
        setPhase('error')
        setError('분석 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.')
        return
      }

      try {
        const log = await getUploadResult(uploadId)

        if (log.status === 'done') {
          stopPolling()
          setResult(log.result)
          setPhase('done')

          // 분석 완료 후 패턴 감지 여부 확인
          const workflows = await getSuggestedWorkflows()
          if (workflows.length > 0) {
            setSuggestedWorkflow(workflows[0])
          }
        } else if (log.status === 'failed') {
          stopPolling()
          setPhase('error')
          setError('AI 분석 중 오류가 발생했습니다. 다시 시도해 주세요.')
        }
      } catch {
        // 폴링 중 일시적 네트워크 오류는 무시하고 재시도
      }
    }, POLL_INTERVAL_MS)
  }, [stopPolling])

  const reset = useCallback(() => {
    stopPolling()
    pollCountRef.current = 0
    setPhase('idle')
    setResult(null)
    setError(null)
    setSuggestedWorkflow(null)
  }, [stopPolling])

  return { phase, result, error, suggestedWorkflow, analyze, reset }
}
