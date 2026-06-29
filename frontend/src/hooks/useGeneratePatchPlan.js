import { useState, useCallback } from 'react'
import { generatePatchPlan } from '../api/documentChanges'

/**
 * AI 패치 플랜 생성 훅.
 * 사용자 프롬프트 → API 발화 → onSuccess 콜백 호출까지 캡슐화한다.
 *
 * @param {number|string|null} uploadId  - 업로드 ID
 * @param {(data: object) => void} onSuccess - 성공 시 호출 (version_id + changes 전달)
 * @returns {{ generate: (prompt: string) => void, isGenerating: boolean, error: string|null }}
 */
export function useGeneratePatchPlan(uploadId, onSuccess) {
  const [isGenerating, setIsGenerating] = useState(false)
  const [error, setError] = useState(null)

  const generate = useCallback(async (prompt) => {
    setIsGenerating(true)
    setError(null)
    try {
      const data = await generatePatchPlan(uploadId, prompt)
      onSuccess(data)
    } catch (err) {
      // 인프라 오류 — try/except로 처리
      setError(err?.message ?? '알 수 없는 오류')
    } finally {
      setIsGenerating(false)
    }
  }, [uploadId, onSuccess])

  return { generate, isGenerating, error }
}
