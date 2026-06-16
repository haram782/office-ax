import { useRef, useEffect, useState, useCallback, useMemo } from 'react'
import { useChat } from './hooks/useChat'
import { FileSidebar, DocViewer, useFileItems } from './components/DocumentPanel'
import { ChatInput } from './components/ChatInput'
import { MessageBubble, TypingIndicator } from './components/MessageBubble'

// ── 빈 상태 ──────────────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center space-y-5 py-16 px-8">
      <div className="w-14 h-14 rounded-2xl bg-blue-600 flex items-center justify-center text-white text-xl font-black shadow-lg shadow-blue-200">
        AX
      </div>
      <div className="space-y-2">
        <h2 className="text-lg font-bold text-gray-900">Office-AX에 오신 것을 환영합니다</h2>
        <p className="text-sm text-gray-500 leading-relaxed max-w-xs">
          Excel이나 PDF 파일을 첨부하면<br />
          AI가 즉시 오류를 검출하고 보정본을 생성합니다.
        </p>
      </div>
      <div className="flex flex-wrap justify-center gap-2 pt-1">
        {[
          '📊 Excel 수식 오류 검출',
          '📄 PDF 내용 요약',
          '🔒 개인정보 자동 마스킹',
          '⬇ 보정 파일 다운로드',
        ].map(tag => (
          <span key={tag} className="text-xs bg-blue-50 text-blue-600 border border-blue-100 rounded-full px-3 py-1">
            {tag}
          </span>
        ))}
      </div>
    </div>
  )
}

// ── App ──────────────────────────────────────────────────────────────────────

export default function App() {
  const { messages, isProcessing, error, sendMessage, resetSession } = useChat()

  /**
   * viewingFileId:
   *   null   → 중앙 뷰어 닫힘 (채팅창이 남은 공간 전체 차지)
   *   number → 해당 upload_log.id의 파일을 중앙 뷰어에 표시
   */
  const [viewingFileId, setViewingFileId] = useState(null)

  const bottomRef = useRef(null)

  // 새 메시지 / 처리 상태 변화 시 하단 스크롤
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isProcessing])

  // 메시지에서 파일 목록 추출 (최신 순)
  const fileItems = useFileItems(messages)
  const hasFiles  = fileItems.length > 0
  const showViewer = viewingFileId !== null

  // 현재 뷰어에 표시 중인 파일 데이터
  const previewData = useMemo(
    () => fileItems.find(f => f.id === viewingFileId) ?? null,
    [fileItems, viewingFileId],
  )

  // 파일 카드 클릭 → 뷰어 오픈
  const handleFileView = useCallback((id) => setViewingFileId(id), [])
  // 뷰어 X → 뷰어 닫기, 채팅창 확장
  const handleCloseViewer = useCallback(() => setViewingFileId(null), [])

  // 팝업과 실시간 동기화:
  // previewData(현재 뷰어 파일)가 바뀔 때마다 localStorage에 기록.
  // AI 분석 완료(artifactUrl 첫 등장)를 감지해 highlightedCells를 포함시키면
  // 팝업의 storage 이벤트가 발화 → 교정 항목 플래시 애니메이션 실행.
  const completedFileIdsRef = useRef(new Set())
  useEffect(() => {
    if (!previewData) return

    const corrections = previewData.snippetData?.corrections ?? []
    const isNewCompletion =
      Boolean(previewData.artifactUrl) &&
      !completedFileIdsRef.current.has(previewData.id)

    if (isNewCompletion) {
      completedFileIdsRef.current.add(previewData.id)
    }

    localStorage.setItem('ax_preview_data', JSON.stringify({
      filename:        previewData.filename,
      fileUrl:         previewData.fileUrl,
      artifactUrl:     previewData.artifactUrl,
      snippetData:     previewData.snippetData,
      // 최초 완료 시에만 하이라이트 셀 목록 포함 → 팝업 플래시 트리거
      highlightedCells: isNewCompletion ? corrections.map(c => c.cell) : [],
      updateId:        Date.now(),
    }))
  }, [previewData])

  return (
    <div className="h-screen flex flex-col bg-white overflow-hidden">

      {/* ── 헤더 (h-12) ── */}
      <header className="flex-shrink-0 h-12 border-b border-gray-200 bg-white/95 backdrop-blur flex items-center px-4 gap-3 z-10">
        <div className="w-7 h-7 rounded-lg bg-blue-600 flex items-center justify-center text-white text-[11px] font-black shadow shadow-blue-200">
          AX
        </div>
        <span className="font-bold text-gray-900 tracking-tight text-sm">Office-AX</span>
        <span className="text-gray-200 text-xs">|</span>
        <span className="text-gray-400 text-xs hidden sm:block">AI 문서 분석 워크스페이스</span>

        <div className="ml-auto flex items-center gap-2">
          {/* 뷰어 닫힌 상태에서 파일 있으면 "뷰어 열기" 힌트 */}
          {hasFiles && !showViewer && (
            <span className="text-[11px] text-gray-300 hidden lg:block">
              파일 목록에서 파일을 클릭하면 문서를 미리볼 수 있습니다
            </span>
          )}

          {messages.length > 0 && (
            <button
              onClick={() => { resetSession(); setViewingFileId(null) }}
              className="text-xs text-gray-400 hover:text-gray-600 border border-gray-200 hover:border-gray-300 rounded-lg px-3 py-1.5 transition-colors"
            >
              새 대화
            </button>
          )}
        </div>
      </header>

      {/* ── 3-컬럼 워크스페이스 ── */}
      <div className="flex-1 flex overflow-hidden">

        {/*
          ┌──────────────┬────────────────────────────┬──────────────────────┐
          │  1열: 파일   │  2열: 문서 뷰어 (중앙)      │  3열: AI 채팅 (우측)  │
          │  사이드바    │  flex-[11] ≈ 55%            │  flex-[9] ≈ 45%      │
          │  w-64 고정   │  파일 선택 시만 표시         │  항상 표시            │
          └──────────────┴────────────────────────────┴──────────────────────┘
        */}

        {/* ── 1열: 파일 목록 사이드바 (w-64 고정, 파일 있을 때만) ── */}
        {hasFiles && (
          <div className="hidden lg:flex w-64 flex-shrink-0 flex-col border-r border-gray-200">
            <FileSidebar
              fileItems={fileItems}
              viewingFileId={viewingFileId}
              onFileView={handleFileView}
            />
          </div>
        )}

        {/* ── 2열: 문서 뷰어 — viewingFileId 있을 때만 렌더 ── */}
        {showViewer && previewData && (
          <div className="hidden lg:flex flex-[11] min-w-0 flex-col border-r border-gray-200">
            <DocViewer
              previewData={previewData}
              onClose={handleCloseViewer}
            />
          </div>
        )}

        {/* ── 3열: AI 채팅 ── */}
        <div className={`flex-1 ${showViewer ? 'lg:flex-[9]' : ''} min-w-0 flex flex-col overflow-hidden bg-gray-50/30`}>

          {/* 파일 있고 뷰어 닫혔을 때 — 모바일에서 간단한 파일 리스트 토글 */}
          {hasFiles && !showViewer && fileItems.length > 0 && (
            <div className="flex-shrink-0 lg:hidden border-b border-gray-200 bg-white">
              <div className="px-4 py-2 flex gap-1.5 overflow-x-auto">
                {fileItems.map(f => (
                  <button
                    key={f.id}
                    onClick={() => handleFileView(f.id)}
                    className="flex-shrink-0 flex items-center gap-1 text-xs bg-white border border-gray-200 rounded-lg px-2.5 py-1.5 hover:border-blue-300 transition-colors"
                  >
                    <span>{f.filename.endsWith('.xlsx') ? '📊' : '📄'}</span>
                    <span className="max-w-[100px] truncate text-gray-700">{f.filename}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* 메시지 목록 */}
          <div className="flex-1 overflow-y-auto px-4 py-5 space-y-5">
            {messages.length === 0 ? (
              <EmptyState />
            ) : (
              messages.map(msg => (
                <MessageBubble
                  key={msg.id}
                  message={msg}
                  onFileView={handleFileView}
                />
              ))
            )}

            {/* 처리 중 로딩 인디케이터 */}
            {isProcessing && <TypingIndicator />}

            {/* 오류 인라인 배너 */}
            {error && (
              <div className="flex justify-center">
                <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-xl px-4 py-3 max-w-sm text-center leading-relaxed">
                  ⚠️ {error}
                </div>
              </div>
            )}

            <div ref={bottomRef} />
          </div>

          {/* 채팅 입력창 */}
          <ChatInput onSend={sendMessage} isProcessing={isProcessing} />
        </div>
      </div>
    </div>
  )
}
