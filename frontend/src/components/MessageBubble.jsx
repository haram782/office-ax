import { useState, useEffect, useCallback } from 'react'

// 파일 분석 로딩 스텝
const FILE_LOADING_STEPS = [
  '📁 문서를 안전하게 업로드하는 중...',
  '🔍 내장 엔진으로 서류 데이터를 정밀 분석하는 중...',
  '🤖 AI가 오류 교정 및 수정본을 작성하는 중...',
]

// 텍스트 채팅 로딩 스텝
const CHAT_LOADING_STEPS = [
  'Gemini가 응답을 생성하는 중...',
  '잠시만 기다려주세요...',
]

/** 마크다운 **bold** 를 <strong>으로 변환하는 최소 렌더러 */
function renderContent(text) {
  return text.split('\n').map((line, i) => {
    const parts = line.split(/(\*\*[^*]+\*\*)/)
    return (
      <p key={i} className={line.startsWith('•') ? 'pl-1' : ''}>
        {parts.map((part, j) =>
          part.startsWith('**') && part.endsWith('**')
            ? <strong key={j}>{part.slice(2, -2)}</strong>
            : part
        )}
      </p>
    )
  })
}

/** Excel 교정 인라인 스니펫 카드. 클릭하면 좌측 패널에서 해당 파일이 열린다. */
function SnippetCard({ snippetData, onFileView }) {
  if (!snippetData || snippetData.type !== 'excel_preview') return null

  const handleClick = () => {
    if (snippetData.upload_log_id && onFileView) {
      onFileView(snippetData.upload_log_id)
    }
  }

  return (
    <div
      onClick={handleClick}
      className="mt-2 rounded-xl border border-blue-200 bg-blue-50/50 overflow-hidden cursor-pointer hover:border-blue-400 hover:bg-blue-50 transition-colors"
    >
      {/* 헤더 */}
      <div className="px-3 py-2 bg-blue-100 flex items-center justify-between">
        <span className="text-xs font-semibold text-blue-700">📊 수정 내용 미리보기</span>
        {snippetData.upload_log_id && onFileView && (
          <span className="text-[11px] text-blue-500">전체 보기 →</span>
        )}
      </div>

      {/* 미니 테이블 */}
      <div className="overflow-x-auto">
        <table className="text-xs w-full">
          <thead>
            <tr className="bg-blue-50/80">
              {(snippetData.headers || []).map((h, i) => (
                <th key={i} className="px-2 py-1.5 text-left font-semibold text-zinc-600 dark:text-zinc-300 whitespace-nowrap border-b border-blue-100">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(snippetData.preview_rows || []).slice(0, 4).map((row, i) => (
              <tr key={i} className="border-t border-blue-100/60 hover:bg-blue-50/30">
                {row.map((cell, j) => (
                  <td key={j} className="px-2 py-1.5 text-zinc-700 dark:text-zinc-200 whitespace-nowrap">
                    {typeof cell === 'number' ? cell.toLocaleString() : cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 수정 항목 요약 */}
      {(snippetData.corrections || []).length > 0 && (
        <div className="px-3 py-2 border-t border-blue-200 bg-white dark:bg-zinc-800">
          <div className="text-[11px] font-semibold text-red-500 mb-1.5">⚠ 감지된 오류 및 수정 사항</div>
          <div className="space-y-1">
            {snippetData.corrections.slice(0, 4).map((c, i) => (
              <div key={i} className="flex items-center gap-2 text-[11px]">
                <span className="font-mono text-zinc-500 dark:text-zinc-400 w-8 flex-shrink-0">{c.cell}</span>
                <span className="text-red-400 line-through truncate max-w-[80px]">{c.original}</span>
                <span className="text-zinc-400">→</span>
                <span className="text-emerald-600 font-medium truncate max-w-[80px]">{c.corrected}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

/**
 * patch_plan 전용 말풍선.
 * source_type='patch_plan'인 어시스턴트 메시지에만 사용한다.
 * snippet_data.patch_changes 개수와 [전체 반영][보류] 액션 버튼을 표시한다.
 */
function PatchPlanBubble({ message, onAcceptPatch, onRejectPatch }) {
  const [isAccepting, setIsAccepting] = useState(false)
  const { content, snippet_data } = message
  // BE는 snippet_data.changes로 저장 — patch_changes는 구버전 키
  const patchCount = (snippet_data?.changes ?? snippet_data?.patch_changes)?.length ?? 0

  const handleAccept = useCallback(async () => {
    if (isAccepting) return
    setIsAccepting(true)
    try {
      await onAcceptPatch?.()
    } finally {
      setIsAccepting(false)
    }
  }, [isAccepting, onAcceptPatch])

  return (
    <div className="rounded-2xl rounded-bl-sm border border-blue-200 dark:border-blue-700 bg-blue-50/50 dark:bg-blue-900/20 shadow-sm overflow-hidden">
      {/* 메시지 본문 */}
      {content && (
        <div className="px-4 pt-3 pb-2 text-sm text-zinc-800 dark:text-zinc-100 leading-relaxed space-y-1">
          {renderContent(content)}
        </div>
      )}

      {/* 변경사항 수 요약 배지 — patch_changes가 1개 이상일 때만 표시 */}
      {patchCount > 0 && (
        <div className="px-4 py-1.5 border-t border-blue-200/60 dark:border-blue-700/60">
          <span className="text-xs text-blue-600 dark:text-blue-400 font-medium">
            📝 {patchCount}개 변경사항 준비됨
          </span>
        </div>
      )}

      {/* 전체 반영 / 보류 버튼 */}
      <div className="px-4 py-2.5 border-t border-blue-200/60 dark:border-blue-700/60 flex gap-2">
        <button
          onClick={handleAccept}
          disabled={isAccepting}
          className="flex-1 flex items-center justify-center gap-1.5 text-xs font-semibold py-1.5 px-3 rounded-lg bg-blue-600 hover:bg-blue-700 text-white transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
        >
          {isAccepting && (
            <span className="w-3 h-3 border border-white border-t-transparent rounded-full animate-spin" />
          )}
          전체 반영
        </button>
        <button
          onClick={() => onRejectPatch?.()}
          disabled={isAccepting}
          className="flex-1 text-xs font-semibold py-1.5 px-3 rounded-lg border border-zinc-300 dark:border-zinc-600 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
        >
          보류
        </button>
      </div>
    </div>
  )
}

export function MessageBubble({ message, onFileView, onAcceptPatch, onRejectPatch }) {
  const isUser = message.role === 'user'
  const isPending = message._pending

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} animate-fade-in-scale`}>
      {/* 어시스턴트 아바타 */}
      {!isUser && (
        <div className="flex-shrink-0 w-7 h-7 rounded-lg bg-blue-600 flex items-center justify-center text-white text-[10px] font-black mr-2 mt-1">
          AX
        </div>
      )}

      <div className="max-w-[78%] space-y-1.5">
        {/* 첨부 파일 이름 배지 */}
        {message.upload_log && (
          <div className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-xl w-fit
            ${isUser ? 'bg-blue-500 text-blue-100 ml-auto' : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300'}`}
          >
            <span>📎</span>
            <span className="truncate max-w-[200px]">{message.upload_log.original_filename}</span>
            {isPending && <span className="opacity-60">· 처리 중…</span>}
          </div>
        )}

        {/* patch_plan 메시지 — 전체 반영/보류 액션 버튼 말풍선 */}
        {!isUser && message.snippet_data?.type === 'patch_plan' ? (
          <PatchPlanBubble
            message={message}
            onAcceptPatch={onAcceptPatch}
            onRejectPatch={onRejectPatch}
          />
        ) : (
          /* 일반 말풍선 */
          message.content && (
            <div className={`rounded-2xl px-4 py-3 text-sm leading-relaxed space-y-1
              ${isUser
                ? 'bg-blue-600 text-white rounded-br-sm'
                : 'bg-zinc-50 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-800 text-zinc-800 dark:text-zinc-100 rounded-bl-sm shadow-sm'
              }
              ${isPending ? 'opacity-60' : ''}
            `}>
              {renderContent(message.content)}
            </div>
          )
        )}

        {/* Excel 교정 스니펫 카드 (어시스턴트 + patch_plan 아닌 경우에만) */}
        {!isUser && message.snippet_data?.type !== 'patch_plan' && message.has_snippet && message.snippet_data && (
          <SnippetCard snippetData={message.snippet_data} onFileView={onFileView} />
        )}

        {/* 보정 파일 다운로드 */}
        {message.artifact_url && (
          <a
            href={message.artifact_url}
            download
            className="flex items-center gap-2 text-xs bg-emerald-500 hover:bg-emerald-600 text-white rounded-xl px-3 py-2 w-fit transition-colors shadow-sm"
          >
            <span>⬇</span>
            <span>보정된 파일 다운로드</span>
          </a>
        )}

        {/* 타임스탬프 */}
        <p className={`text-[10px] text-zinc-400 ${isUser ? 'text-right' : 'text-left'}`}>
          {new Date(message.created_at).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })}
        </p>
      </div>
    </div>
  )
}

/**
 * 로딩 인디케이터.
 * mode="file"(기본): 파일 분석 단계별 메시지
 * mode="chat": 텍스트 채팅 대기 메시지
 */
export function TypingIndicator({ mode = 'file' }) {
  const steps = mode === 'chat' ? CHAT_LOADING_STEPS : FILE_LOADING_STEPS
  const [stepIdx, setStepIdx] = useState(0)

  useEffect(() => {
    // mode 변경 시 스텝 초기화
    setStepIdx(0)
    const id = setInterval(() => {
      setStepIdx(prev => prev < steps.length - 1 ? prev + 1 : 1)
    }, 1000)
    return () => clearInterval(id)
  }, [mode, steps.length])

  return (
    <div className="flex justify-start items-end gap-2">
      <div className="w-7 h-7 rounded-lg bg-blue-600 flex items-center justify-center text-white text-[10px] font-black flex-shrink-0">
        AX
      </div>
      {/* max-w-max → 콘텐츠 너비만큼만 */}
      <div className="max-w-max flex items-center gap-2 bg-zinc-100 dark:bg-zinc-800 p-3 rounded-2xl">
        <p key={stepIdx} className="text-sm text-zinc-600 dark:text-zinc-300 animate-fade-in-scale whitespace-nowrap">
          {steps[stepIdx]}
        </p>
        <div className="flex gap-1 items-center">
          {[0, 150, 300].map(delay => (
            <span
              key={delay}
              className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce flex-shrink-0"
              style={{ animationDelay: `${delay}ms` }}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
