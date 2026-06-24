import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'

import { Topbar }             from '../../components/Topbar'
import { useChat }            from '../../hooks/useChat'
import { useFileItems }       from '../../components/DocumentPanel'

import { WorkspaceSidebar }   from './WorkspaceSidebar'
import { WorkspaceCenter }    from './WorkspaceCenter'
import { WorkspaceChat }      from './WorkspaceChat'
import { SubViewerPopup }     from './SubViewerPopup'

// 사이드바에 표시할 더미 대화 목록 (BE 완성 후 API로 교체)
const INITIAL_CONVERSATIONS = [
  { id: 'c1',  title: '청약신청서 접수증 분석', ts: '오전 02:17' },
  { id: 'c0b', title: '견적서 수식 오류 검토',  ts: '어제 18:40' },
  { id: 'c0a', title: '계약서 개인정보 마스킹', ts: '어제 14:02' },
]

/**
 * 워크스페이스 페이지.
 * useChat(실제 API) + 더미 사이드바 대화 목록 + resolveViewer 연결.
 */
export default function Workspace() {
  const navigate  = useNavigate()
  const { messages, isProcessing, error, sendMessage, resetSession } = useChat()

  // 중앙 뷰어에 표시 중인 파일 ID
  const [viewingFileId, setViewingFileId] = useState(null)
  const fileItems  = useFileItems(messages)
  const previewData = useMemo(
    () => fileItems.find(f => f.id === viewingFileId) ?? null,
    [fileItems, viewingFileId],
  )

  // 더미 대화 목록 상태
  const [conversations, setConversations] = useState(INITIAL_CONVERSATIONS)
  const [activeConv, setActiveConv]       = useState('c1')

  // 자동화 규칙 체크박스
  const [rules, setRules] = useState({ table: true, date: true, mask: false, tone: true })
  const activeRuleCount   = Object.values(rules).filter(Boolean).length

  // RAG 선택
  const [ragTone, setRagTone] = useState('하람_보고서_스타일')
  const [ragForm, setRagForm] = useState('회사_기획서_양식')

  // 서브뷰어 팝업 / 자동화 배너
  const [showPopup,  setShowPopup]  = useState(false)
  const [showBanner, setShowBanner] = useState(false)

  // 새 대화 생성 — 더미 목록에 추가하고 세션 리셋
  const handleNewConversation = useCallback(() => {
    const id = `c${Date.now()}`
    setConversations(prev => [{ id, title: '새 대화', ts: '방금' }, ...prev])
    setActiveConv(id)
    setViewingFileId(null)
    resetSession()
  }, [resetSession])

  const toggleRule = useCallback((key) => {
    setRules(prev => ({ ...prev, [key]: !prev[key] }))
  }, [])

  // localStorage 동기화 — PreviewPage 팝업창과 실시간 연동
  const completedFileIdsRef = useRef(new Set())
  useEffect(() => {
    if (!previewData) return
    const corrections    = previewData.snippetData?.corrections ?? []
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

  // 현재 활성 대화 제목
  const activeConvTitle = conversations.find(c => c.id === activeConv)?.title ?? '새 대화'

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      <Topbar onNewConversation={handleNewConversation} />

      <div className="flex-1 flex overflow-hidden">
        {/* 1열: 좌측 사이드바 */}
        <WorkspaceSidebar
          conversations={conversations}
          activeConv={activeConv}
          onSelectConversation={setActiveConv}
          onNewConversation={handleNewConversation}
          fileItems={fileItems}
          viewingFileId={viewingFileId}
          onFileView={setViewingFileId}
          rules={rules}
          onToggleRule={toggleRule}
          activeRuleCount={activeRuleCount}
        />

        {/* 2열: 중앙 뷰어 — 파일 선택 시 표시, 닫혀 있으면 빈 flex-1로 채팅을 오른쪽에 고정 */}
        {previewData ? (
          <WorkspaceCenter
            key={viewingFileId}
            previewData={previewData}
            onCloseViewer={() => setViewingFileId(null)}
            onOpenPopup={() => setShowPopup(true)}
            showBanner={showBanner}
            onDismissBanner={() => setShowBanner(false)}
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
          ragTone={ragTone}
          ragForm={ragForm}
          onRagToneChange={setRagTone}
          onRagFormChange={setRagForm}
          onTriggerBanner={() => setShowBanner(true)}
          activeConvTitle={activeConvTitle}
          onNewConversation={handleNewConversation}
        />
      </div>

      {/* 서브뷰어 팝업 */}
      {showPopup && previewData && (
        <SubViewerPopup
          previewData={previewData}
          isFixed={false}
          onClose={() => setShowPopup(false)}
        />
      )}
    </div>
  )
}
