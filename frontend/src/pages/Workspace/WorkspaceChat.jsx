import { useRef, useEffect } from 'react'
import { Ic }              from '../../components/Ic'
import { ChatInput }       from '../../components/ChatInput'
import { MessageBubble, TypingIndicator } from '../../components/MessageBubble'
import { RagSelector }     from './RagSelector'

/** 빈 대화 환영 화면 */
function WelcomeScreen({ onChipClick }) {
  const chips = [
    { label: '날짜 형식 통일',    key: 'date',     icon: 'history'   },
    { label: '표 서식 정렬',      key: 'table',    icon: 'layout'    },
    { label: '개인정보 마스킹',   key: 'mask',     icon: 'sparkles'  },
    { label: '보정 파일 다운로드', key: 'download', icon: 'download'  },
  ]
  return (
    <div className="flex-1 flex flex-col items-center justify-center text-center px-6">
      <div className="w-14 h-14 rounded-2xl bg-blue-600 text-white grid place-items-center text-base font-bold mb-4">
        AX
      </div>
      <div className="text-base font-bold text-zinc-800 dark:text-zinc-100">Office-AX에 오신 것을 환영합니다</div>
      <p className="text-sm text-zinc-400 mt-1.5 leading-relaxed">
        파일을 첨부하면 AI가 즉시 오류를 검출하고 보정본을 생성합니다.
      </p>
      <div className="flex flex-wrap justify-center gap-2 mt-5">
        {chips.map(c => (
          <button
            key={c.key}
            onClick={() => onChipClick?.(c.key)}
            className="inline-flex items-center gap-1.5 rounded-full border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 hover:bg-zinc-50 dark:hover:bg-zinc-700 text-[11px] px-2.5 py-1 text-zinc-600 dark:text-zinc-300"
          >
            <Ic name={c.icon} className="w-3.5 h-3.5" />
            {c.label}
          </button>
        ))}
      </div>
    </div>
  )
}

/**
 * 워크스페이스 우측 AI 채팅 패널.
 * useChat 훅과 연결되어 실제 메시지 송수신을 처리한다.
 *
 * @param {{
 *   messages: Array,
 *   isProcessing: boolean,
 *   error: string|null,
 *   onSend: Function,
 *   onFileView: Function,
 *   ragTone: string,
 *   ragForm: string,
 *   onRagToneChange: Function,
 *   onRagFormChange: Function,
 *   onTriggerBanner: Function,
 *   activeConvTitle: string,
 *   onNewConversation: Function,
 * }} props
 */
export function WorkspaceChat({
  messages,
  isProcessing,
  error,
  onSend,
  onFileView,
  ragTone,
  ragForm,
  onRagToneChange,
  onRagFormChange,
  onTriggerBanner,
  activeConvTitle,
  onNewConversation,
}) {
  const bottomRef = useRef(null)

  // 새 메시지 도착 시 하단 스크롤
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isProcessing])

  // 빠른 칩 → 미리 정의된 텍스트 전송
  function handleChip(key) {
    const presets = {
      date:     '날짜 형식을 YYYY-MM-DD로 통일해줘',
      table:    '표 셀 서식을 자동 정렬해줘',
      mask:     '개인정보를 자동 마스킹해줘',
      download: '보정된 파일을 다운로드하고 싶어',
      repeat:   '반복 작업으로 등록하고 싶어',
    }
    if (presets[key]) onSend(presets[key], [])
  }

  return (
    /* 채팅 패널 — 우측 고정폭 680px */
    <aside className="w-[680px] shrink-0 border-l border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 flex flex-col">
      {/* 채팅 헤더 */}
      <div className="h-11 shrink-0 flex items-center justify-between px-4 border-b border-zinc-200 dark:border-zinc-800">
        <div className="flex items-center gap-2 min-w-0">
          <Ic name="bot" className="w-4 h-4 text-blue-600 shrink-0" />
          <span className="text-sm font-semibold text-zinc-700 dark:text-zinc-200 truncate">
            {activeConvTitle}
          </span>
        </div>
        <button
          onClick={onNewConversation}
          title="새 대화"
          className="shrink-0 w-11 h-11 min-w-[44px] min-h-[44px] grid place-items-center rounded-lg text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800"
        >
          <Ic name="plus" />
        </button>
      </div>

      {/* 메시지 목록 또는 환영 화면 */}
      {messages.length === 0 && !isProcessing
        ? <WelcomeScreen onChipClick={handleChip} />
        : (
          <div className="flex-1 overflow-auto p-4 flex flex-col gap-4">
            {messages.map(msg => (
              <MessageBubble key={msg.id} message={msg} onFileView={onFileView} />
            ))}
            {isProcessing && <TypingIndicator />}
            {error && (
              <div className="flex justify-center">
                <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-xl px-4 py-3 max-w-sm text-center">
                  ⚠️ {error}
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        )
      }

      {/* 하단 입력 패널 */}
      <div className="shrink-0 border-t border-zinc-200 dark:border-zinc-800">
        {/* RAG 선택기 */}
        <RagSelector
          ragTone={ragTone}
          ragForm={ragForm}
          onToneChange={onRagToneChange}
          onFormChange={onRagFormChange}
        />

        {/* 빠른 칩 */}
        <div className="px-3 pt-2.5 flex flex-wrap gap-1.5">
          {[
            { label: '날짜 형식 통일', key: 'date',   icon: 'history'  },
            { label: '표 서식 정렬',   key: 'table',  icon: 'layout'   },
            { label: '반복 작업 실행', key: 'repeat', icon: 'zap', extra: onTriggerBanner },
          ].map(c => (
            <button
              key={c.key}
              onClick={() => { c.extra?.(); handleChip(c.key) }}
              className="inline-flex items-center gap-1.5 rounded-full border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 hover:bg-zinc-50 dark:hover:bg-zinc-700 text-[11px] px-2.5 py-1 text-zinc-600 dark:text-zinc-300"
            >
              <Ic name={c.icon} className="w-3.5 h-3.5" />
              {c.label}
            </button>
          ))}
        </div>

        {/* 채팅 입력 */}
        <ChatInput onSend={onSend} isProcessing={isProcessing} />
      </div>
    </aside>
  )
}
