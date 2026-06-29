import { useState } from 'react'

/**
 * 문서 수정 요청 입력 컴포넌트.
 * uploadId가 없으면 렌더링하지 않는다.
 *
 * @param {{
 *   uploadId:     number|string|null,
 *   onGenerate:   (prompt: string) => void,
 *   isGenerating: boolean,
 *   error:        string|null,
 * }} props
 */
export function PatchRequestInput({ uploadId, onGenerate, isGenerating, error = null }) {
  const [prompt, setPrompt] = useState('')

  // uploadId 없으면 렌더하지 않는다
  if (!uploadId) return null

  const canSend = prompt.trim().length > 0 && !isGenerating

  const handleSend = () => {
    if (!canSend) return
    onGenerate(prompt.trim())
    setPrompt('')
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="flex-shrink-0 border-t border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 py-2.5">
      <p className="text-[10px] font-bold text-zinc-500 dark:text-zinc-400 mb-1.5">
        수정 요청
      </p>
      <div className="flex gap-1.5 items-end">
        <textarea
          className="flex-1 resize-none text-xs rounded-md border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800 text-zinc-800 dark:text-zinc-200 px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-blue-400 dark:focus:ring-blue-600 placeholder-zinc-400"
          placeholder="수정 내용을 입력하세요 (예: 표 헤더를 굵게)"
          rows={2}
          value={prompt}
          onChange={e => setPrompt(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isGenerating}
        />
        <button
          onClick={handleSend}
          disabled={!canSend}
          className="flex-shrink-0 text-[11px] font-medium px-2.5 py-1.5 rounded-md border transition-colors
            disabled:opacity-40 disabled:cursor-not-allowed
            text-blue-600 dark:text-blue-400 border-blue-200 dark:border-blue-700
            hover:border-blue-300 dark:hover:border-blue-500
            enabled:hover:bg-blue-50 dark:enabled:hover:bg-blue-900/20"
        >
          {isGenerating ? (
            <span className="inline-block w-3 h-3 border border-current border-t-transparent rounded-full animate-spin" />
          ) : '생성'}
        </button>
      </div>
      {/* 오류 메시지 */}
      {error && (
        <p className="mt-1 text-[10px] text-red-500">{error}</p>
      )}
    </div>
  )
}
