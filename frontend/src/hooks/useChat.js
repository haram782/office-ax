import { useState, useCallback, useRef, useEffect } from 'react'
import { createChatSession, getChatSessions, getChatMessages, sendChatMessage } from '../api/client'

const POLL_INTERVAL_MS = 2500
const MAX_POLLS = 40   // 100초 타임아웃

function makeConvId() { return `conv_${Date.now()}` }

/**
 * 채팅 워크스페이스 상태 머신 — sessions 맵 구조.
 *
 * sessions: Record<convId, { messages, title, ts }>
 *   각 대화(conversation)를 독립적인 메시지 목록으로 관리한다.
 * activeSessionId: 현재 선택된 대화 ID.
 *
 * 무한 루프 방지:
 *   전송 전 baseline 어시스턴트 수 → targetCount = baseline + 파일 수.
 *   targetCount 도달 시 즉시 폴링 종료.
 */
export function useChat() {
  const initId = useRef(makeConvId())

  // 세션 맵: { [convId]: { messages, title, ts } }
  const [sessions, setSessions] = useState(() => ({
    [initId.current]: { messages: [], title: '새 대화', ts: '방금' },
  }))
  const [activeSessionId, setActiveSessionId] = useState(initId.current)
  const [isProcessing, setIsProcessing]       = useState(false)
  const [isLoadingSessions, setIsLoadingSessions] = useState(true)
  const [error, setError]                     = useState(null)

  // 백엔드 세션 ID 맵 (렌더 외부 — 클로저 안전)
  const backendIdsRef = useRef({})   // { [convId]: string }
  const intervalRef   = useRef(null)
  const pollCountRef  = useRef(0)

  const stopPolling = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
  }, [])

  useEffect(() => () => stopPolling(), [stopPolling])

  // 마운트 시 백엔드에 저장된 세션 목록을 불러와 sessions 맵을 초기화한다
  useEffect(() => {
    getChatSessions()
      .then(list => {
        if (list.length === 0) {
          // 신규 유저 — 초기 빈 세션 유지
          setIsLoadingSessions(false)
          return
        }

        // 최신순 정렬 (백엔드 응답이 최신순이어도 명시적으로 보장)
        const sorted = [...list].sort(
          (a, b) => new Date(b.updated_at) - new Date(a.updated_at)
        )

        // sessions 맵 구성: convId = String(backendId)
        const newSessions = {}
        sorted.forEach(s => {
          newSessions[String(s.id)] = {
            messages: s.messages ?? [],
            title:    s.title || '새 대화',
            ts:       s.updated_at,
          }
        })

        // backendIdsRef 동기화: convId → 백엔드 정수 ID
        sorted.forEach(s => {
          backendIdsRef.current[String(s.id)] = s.id
        })

        setSessions(newSessions)
        setActiveSessionId(String(sorted[0].id))
      })
      .catch(() => {
        // 로드 실패 시 초기 빈 세션 유지 — 데이터 유실 없음
      })
      .finally(() => {
        setIsLoadingSessions(false)
      })
  }, [])  // 마운트 1회만 실행

  // 활성 세션 메시지 (파생)
  const messages = sessions[activeSessionId]?.messages ?? []

  // 세션 메시지 갱신 헬퍼
  const setConvMessages = useCallback((convId, msgs) => {
    setSessions(prev => ({
      ...prev,
      [convId]: { ...prev[convId], messages: msgs },
    }))
  }, [])

  // 백엔드 세션 ID 획득 (없으면 생성)
  const getOrCreateBackendId = useCallback(async (convId) => {
    if (backendIdsRef.current[convId]) return backendIdsRef.current[convId]
    const session = await createChatSession()
    backendIdsRef.current[convId] = session.id
    return session.id
  }, [])

  // 새 대화 생성 — sessions 맵에 추가하고 activeSessionId 변경
  const createSession = useCallback((title = '새 대화') => {
    const id = makeConvId()
    setSessions(prev => ({ ...prev, [id]: { messages: [], title, ts: '방금' } }))
    setActiveSessionId(id)
    stopPolling()
    setIsProcessing(false)
    setError(null)
    return id
  }, [stopPolling])

  // 대화 전환 — 다른 convId 선택
  const switchSession = useCallback((convId) => {
    stopPolling()
    setActiveSessionId(convId)
    setIsProcessing(false)
    setError(null)
  }, [stopPolling])

  // 메시지 전송 — uploadId는 현재 열려 있는 문서의 upload_log.id (없으면 null)
  const sendMessage = useCallback(async (content, files = [], uploadId = null) => {
    const convId = activeSessionId
    if (!convId) return

    const fileList = Array.isArray(files)
      ? files.filter(Boolean)
      : (files ? [files] : [])

    setError(null)
    setIsProcessing(true)
    stopPolling()
    pollCountRef.current = 0

    let sid
    try {
      sid = await getOrCreateBackendId(convId)
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

    setSessions(prev => ({
      ...prev,
      [convId]: { ...prev[convId], messages: [...(prev[convId]?.messages ?? []), ...tempMsgs] },
    }))

    try {
      // ── 텍스트 전용 — Gemini 응답을 폴링으로 대기 ──────────────────────────
      if (fileList.length === 0) {
        // 전송 전 어시스턴트 수 baseline 기록
        const beforeMsgs = await getChatMessages(sid)
        const baselineAssistantCount = beforeMsgs.filter(m => m.role === 'assistant').length
        const targetAssistantCount   = baselineAssistantCount + 1

        await sendChatMessage(sid, content, null, uploadId)

        const afterSendMsgs = await getChatMessages(sid)
        setConvMessages(convId, afterSendMsgs)

        // 동기 응답(mock 등)이 즉시 왔으면 폴링 불필요
        if (afterSendMsgs.filter(m => m.role === 'assistant').length >= targetAssistantCount) {
          setIsProcessing(false)
          return
        }

        // Celery text_chat 태스크 완료까지 폴링
        intervalRef.current = setInterval(async () => {
          pollCountRef.current += 1

          if (pollCountRef.current > MAX_POLLS) {
            stopPolling()
            setIsProcessing(false)
            setError('응답 시간이 초과되었습니다. 잠시 후 다시 시도해주세요.')
            return
          }

          try {
            const fresh = await getChatMessages(sid)
            setConvMessages(convId, fresh)
            if (fresh.filter(m => m.role === 'assistant').length >= targetAssistantCount) {
              stopPolling()
              setIsProcessing(false)
            }
          } catch { /* 일시적 네트워크 오류 무시 */ }
        }, POLL_INTERVAL_MS)
        return
      }

      // ── 파일 전송 ────────────────────────────────────────────────────────────
      const beforeMsgs = await getChatMessages(sid)
      const baselineAssistantCount = beforeMsgs.filter(m => m.role === 'assistant').length
      const targetAssistantCount   = baselineAssistantCount + fileList.length

      for (let i = 0; i < fileList.length; i++) {
        await sendChatMessage(sid, i === 0 ? content : '', fileList[i], uploadId)
      }

      const afterSendMsgs = await getChatMessages(sid)
      setConvMessages(convId, afterSendMsgs)

      // 중복 파일 dedup: 즉시 완료 여부 확인
      if (afterSendMsgs.filter(m => m.role === 'assistant').length >= targetAssistantCount) {
        setIsProcessing(false)
        return
      }

      // ── Celery 완료 폴링 ─────────────────────────────────────────────────────
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
          setConvMessages(convId, fresh)
          if (fresh.filter(m => m.role === 'assistant').length >= targetAssistantCount) {
            stopPolling()
            setIsProcessing(false)
          }
        } catch { /* 일시적 네트워크 오류 무시 */ }
      }, POLL_INTERVAL_MS)

    } catch (err) {
      setSessions(prev => ({
        ...prev,
        [convId]: {
          ...prev[convId],
          messages: (prev[convId]?.messages ?? []).filter(m => !m._pending),
        },
      }))
      setIsProcessing(false)
      setError(err?.response?.data?.error ?? '메시지 전송에 실패했습니다.')
    }
  }, [activeSessionId, getOrCreateBackendId, setConvMessages, stopPolling])

  // resetSession — createSession의 별칭 (하위 호환)
  const resetSession = useCallback(() => createSession(), [createSession])

  return {
    sessions,
    activeSessionId,
    messages,
    isProcessing,
    isLoadingSessions,
    error,
    sendMessage,
    createSession,
    switchSession,
    resetSession,
  }
}
