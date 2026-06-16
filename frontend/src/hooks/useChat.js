import { useState, useCallback, useRef, useEffect } from 'react'
import { createChatSession, getChatMessages, sendChatMessage } from '../api/client'

const POLL_INTERVAL_MS = 2500
const MAX_POLLS = 40   // 100초 타임아웃

/**
 * 채팅 워크스페이스 상태 머신.
 *
 * 무한 루프 방지:
 *   - 전송 전 어시스턴트 메시지 수(baseline)를 확인
 *   - targetCount = baseline + 파일 수
 *   - 어시스턴트 메시지가 targetCount에 도달하면 즉시 폴링 종료
 *   - 중복 파일(dedup)인 경우 백엔드가 즉시 어시스턴트 메시지를 생성하므로
 *     첫 번째 폴링에서 바로 종료됨
 */
export function useChat() {
  const [sessionId, setSessionId] = useState(null)
  const [messages, setMessages] = useState([])
  const [isProcessing, setIsProcessing] = useState(false)
  const [error, setError] = useState(null)

  const intervalRef = useRef(null)
  const pollCountRef = useRef(0)
  const sessionIdRef = useRef(null)   // ref로도 보관 — interval closure 용

  const stopPolling = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
  }, [])

  useEffect(() => () => stopPolling(), [stopPolling])

  const getOrCreateSession = useCallback(async () => {
    if (sessionIdRef.current) return sessionIdRef.current
    const session = await createChatSession()
    sessionIdRef.current = session.id
    setSessionId(session.id)
    return session.id
  }, [])

  const sendMessage = useCallback(async (content, files = []) => {
    const fileList = Array.isArray(files)
      ? files.filter(Boolean)
      : (files ? [files] : [])

    setError(null)
    setIsProcessing(true)
    stopPolling()
    pollCountRef.current = 0

    let sid
    try {
      sid = await getOrCreateSession()
    } catch {
      setIsProcessing(false)
      setError('세션 생성에 실패했습니다.')
      return
    }

    // 낙관적 메시지 추가
    const now = Date.now()
    const tempMsgs = fileList.length > 0
      ? fileList.map((f, i) => ({
          id: `pending-${now}-${i}`,
          role: 'user',
          content: i === 0 ? content : '',
          upload_log: { id: null, original_filename: f.name, status: 'processing', file_url: '' },
          artifact_url: '',
          has_snippet: false,
          snippet_data: {},
          created_at: new Date(now + i).toISOString(),
          _pending: true,
        }))
      : [{
          id: `pending-${now}`,
          role: 'user',
          content,
          upload_log: null,
          artifact_url: '',
          has_snippet: false,
          snippet_data: {},
          created_at: new Date(now).toISOString(),
          _pending: true,
        }]

    setMessages(prev => [...prev, ...tempMsgs])

    try {
      // ── 텍스트 전용 ─────────────────────────────────────────────────────────
      if (fileList.length === 0) {
        await sendChatMessage(sid, content, null)
        const fresh = await getChatMessages(sid)
        setMessages(fresh)
        setIsProcessing(false)
        return
      }

      // ── 파일 전송 ───────────────────────────────────────────────────────────
      // 전송 전 기준 어시스턴트 메시지 수 파악 (세션 재개 시 기존 메시지 보정)
      const beforeMsgs = await getChatMessages(sid)
      const baselineAssistantCount = beforeMsgs.filter(m => m.role === 'assistant').length
      const targetAssistantCount = baselineAssistantCount + fileList.length

      // 파일 순차 전송: 첫 파일만 본문 포함
      for (let i = 0; i < fileList.length; i++) {
        await sendChatMessage(sid, i === 0 ? content : '', fileList[i])
      }

      // 전송 직후 상태 갱신
      const afterSendMsgs = await getChatMessages(sid)
      setMessages(afterSendMsgs)

      // 중복 파일 dedup: 백엔드가 즉시 어시스턴트 메시지 생성 → 바로 종료
      const currentAssistantCount = afterSendMsgs.filter(m => m.role === 'assistant').length
      if (currentAssistantCount >= targetAssistantCount) {
        setIsProcessing(false)
        return
      }

      // ── 폴링: Celery 완료 대기 ─────────────────────────────────────────────
      intervalRef.current = setInterval(async () => {
        pollCountRef.current += 1

        if (pollCountRef.current > MAX_POLLS) {
          stopPolling()
          setIsProcessing(false)
          setError('분석 시간이 초과되었습니다. Celery 워커가 실행 중인지 확인하세요.')
          return
        }

        try {
          const fresh = await getChatMessages(sid)
          setMessages(fresh)
          if (fresh.filter(m => m.role === 'assistant').length >= targetAssistantCount) {
            stopPolling()
            setIsProcessing(false)
          }
        } catch { /* 일시적 네트워크 오류 무시 */ }
      }, POLL_INTERVAL_MS)

    } catch (err) {
      setMessages(prev => prev.filter(m => !m._pending))
      setIsProcessing(false)
      setError(err?.response?.data?.error ?? '메시지 전송에 실패했습니다.')
    }
  }, [getOrCreateSession, stopPolling])

  const resetSession = useCallback(() => {
    stopPolling()
    sessionIdRef.current = null
    setSessionId(null)
    setMessages([])
    setIsProcessing(false)
    setError(null)
  }, [stopPolling])

  return { sessionId, messages, isProcessing, error, sendMessage, resetSession }
}
