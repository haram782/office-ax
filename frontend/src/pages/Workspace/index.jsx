import { useState, useRef, useEffect, useCallback, useMemo } from 'react'

import { Topbar }           from '../../components/Topbar'
import { useChat }          from '../../hooks/useChat'
import { useFileItems }     from '../../components/DocumentPanel'

import { WorkspaceSidebar } from './WorkspaceSidebar'
import { WorkspaceCenter }  from './WorkspaceCenter'
import { WorkspaceChat }    from './WorkspaceChat'

/**
 * 워크스페이스 페이지.
 * useChat의 sessions 맵을 사이드바 대화 목록으로 직접 사용한다.
 */
export default function Workspace() {
  const {
    sessions,
    activeSessionId,
    messages,
    isProcessing,
    isLoadingSessions,
    error,
    sendMessage,
    createSession,
    switchSession,
  } = useChat()

  // 중앙 뷰어에 표시 중인 파일 ID
  const [viewingFileId, setViewingFileId] = useState(null)

  // 활성 세션 메시지 기준으로 파일 목록 추출
  const fileItems   = useFileItems(messages)
  const previewData = useMemo(
    () => fileItems.find(f => f.id === viewingFileId) ?? null,
    [fileItems, viewingFileId],
  )

  // 자동화 규칙 체크박스
  const [rules, setRules] = useState({ table: true, date: true, mask: false, tone: true })
  const activeRuleCount   = Object.values(rules).filter(Boolean).length

  // RAG 선택
  const [ragTone, setRagTone] = useState('하람_보고서_스타일')
  const [ragForm, setRagForm] = useState('회사_기획서_양식')

  // 자동화 배너
  const [showBanner, setShowBanner] = useState(false)

  // ── 채팅 patch_plan 연동 ────────────────────────────────────────────────────
  // PatchRequestInput 또는 채팅 patch_plan 메시지로부터 받은 patch 데이터
  // WorkspaceCenter 내부에서 관리하던 것을 채팅 연동을 위해 여기서 관리한다
  const [localPatchData, setLocalPatchData] = useState(null)

  // WorkspaceCenter가 마운트될 때 handleAcceptAll 함수를 등록하는 ref
  // 채팅 [전체 반영] 클릭 시 우측 패널과 동일한 acceptAll 로직을 실행한다
  const acceptAllFnRef = useRef(null)
  const handleAcceptAllReady = useCallback((fn) => {
    acceptAllFnRef.current = fn
  }, [])
  const handleChatAcceptAll = useCallback(async () => {
    await acceptAllFnRef.current?.()
  }, [])

  // 최신 patch_plan 메시지 감지 → localPatchData 자동 설정.
  // viewingFileId가 바뀌면 즉시 재실행해 다른 파일의 patch 데이터가 남지 않도록 한다.
  // upload_id 기준으로 현재 보는 파일과 일치하는 patch_plan만 채택한다.
  useEffect(() => {
    const last = [...messages].reverse().find(
      m => m.snippet_data?.type === 'patch_plan' &&
           (viewingFileId == null || m.snippet_data?.upload_id === viewingFileId),
    )
    if (!last) {
      setLocalPatchData(null)
      return
    }
    const pd = last.snippet_data
    // BE는 snippet_data.changes로 저장 — patch_changes는 구버전 키
    const changes = pd?.changes ?? pd?.patch_changes
    if (Array.isArray(changes)) {
      setLocalPatchData({ version_id: pd.version_id ?? null, patch_changes: changes })
    }
  }, [messages, viewingFileId])

  // 새 대화 생성 — sessions 맵에 추가하고 뷰어 초기화
  const handleNewConversation = useCallback(() => {
    createSession()
    setViewingFileId(null)
  }, [createSession])

  // 대화 전환 — 뷰어 닫기
  const handleSelectConversation = useCallback((convId) => {
    switchSession(convId)
    setViewingFileId(null)
  }, [switchSession])

  const toggleRule = useCallback((key) => {
    setRules(prev => ({ ...prev, [key]: !prev[key] }))
  }, [])

  // localStorage 동기화 — PreviewPage 팝업창과 실시간 연동
  const completedFileIdsRef = useRef(new Set())
  useEffect(() => {
    if (!previewData) return
    const corrections     = previewData.snippetData?.corrections ?? []
    const isNewCompletion = Boolean(previewData.artifactUrl) && !completedFileIdsRef.current.has(previewData.id)
    if (isNewCompletion) completedFileIdsRef.current.add(previewData.id)

    localStorage.setItem('ax_preview_data', JSON.stringify({
      filename:         previewData.filename,
      fileUrl:          previewData.fileUrl,
      artifactUrl:      previewData.artifactUrl,
      snippetData:      previewData.snippetData,
      highlightedCells: isNewCompletion ? corrections.map(c => c.cell) : [],
      updateId:         Date.now(),
    }))
  }, [previewData])

  // sessions 맵 → 사이드바용 배열 (최신순)
  const conversations = useMemo(
    () => Object.entries(sessions).map(([id, s]) => ({ id, title: s.title, ts: s.ts })).reverse(),
    [sessions],
  )
  const activeConvTitle = sessions[activeSessionId]?.title ?? '새 대화'

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      <Topbar onNewConversation={handleNewConversation} />

      <div className="flex-1 flex overflow-hidden">
        {/* 1열: 좌측 사이드바 */}
        <WorkspaceSidebar
          conversations={conversations}
          activeConv={activeSessionId}
          onSelectConversation={handleSelectConversation}
          onNewConversation={handleNewConversation}
          fileItems={fileItems}
          viewingFileId={viewingFileId}
          onFileView={setViewingFileId}
          rules={rules}
          onToggleRule={toggleRule}
          activeRuleCount={activeRuleCount}
          isLoadingSessions={isLoadingSessions}
        />

        {/* 2열: 중앙 뷰어 — 파일 선택 시 표시, 닫혀 있으면 빈 flex-1로 채팅을 오른쪽에 고정 */}
        {previewData ? (
          <WorkspaceCenter
            key={viewingFileId}
            previewData={previewData}
            onCloseViewer={() => setViewingFileId(null)}
            showBanner={showBanner}
            onDismissBanner={() => setShowBanner(false)}
            localPatchData={localPatchData}
            onPatchDataChange={setLocalPatchData}
            onAcceptAllReady={handleAcceptAllReady}
          />
        ) : (
          <div className="flex-1 bg-zinc-100 dark:bg-zinc-950" />
        )}

        {/* 3열: 우측 AI 채팅 — 항상 오른쪽 고정 */}
        <WorkspaceChat
          messages={messages}
          isProcessing={isProcessing}
          error={error}
          onSend={sendMessage}
          onFileView={setViewingFileId}
          uploadId={previewData?.id ?? null}
          onChatAcceptAll={handleChatAcceptAll}
          ragTone={ragTone}
          ragForm={ragForm}
          onRagToneChange={setRagTone}
          onRagFormChange={setRagForm}
          onTriggerBanner={() => setShowBanner(true)}
          activeConvTitle={activeConvTitle}
          onNewConversation={handleNewConversation}
        />
      </div>

    </div>
  )
}
