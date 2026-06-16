import { useState, useRef, useEffect } from 'react'

const _ICON_MAP = { xlsx: '📊', xls: '📊', csv: '📋', pdf: '📄', docx: '📝', doc: '📝', pptx: '📑', hwp: '📄', hwpx: '📄', png: '🖼', jpg: '🖼', jpeg: '🖼', webp: '🖼', gif: '🖼' }
function chipIcon(name) {
  const ext = name.split('.').pop().toLowerCase()
  return _ICON_MAP[ext] ?? '🗂'
}

export function ChatInput({ onSend, isProcessing }) {
  const [text, setText] = useState('')
  const [files, setFiles] = useState([])
  const fileInputRef = useRef(null)
  const textareaRef = useRef(null)

  // textarea 높이 자동 조절
  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 128)}px`
  }, [text])

  const canSend = (text.trim() || files.length > 0) && !isProcessing

  const handleSend = () => {
    if (!canSend) return
    onSend(text.trim(), files)
    setText('')
    setFiles([])
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleFileChange = (e) => {
    const added = Array.from(e.target.files || [])
    if (added.length === 0) return
    setFiles(prev => [...prev, ...added])
    // 파일 선택 완료 즉시 textarea로 포커스 이동 → 엔터 바로 전송 가능
    setTimeout(() => textareaRef.current?.focus(), 0)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const removeFile = (idx) => {
    setFiles(prev => prev.filter((_, i) => i !== idx))
  }

  return (
    <div className="flex-shrink-0 border-t border-gray-200 bg-white px-4 py-3">

      {/* 첨부 파일 칩 목록 */}
      {files.length > 0 && (
        <div className="mb-2.5 flex flex-wrap gap-1.5">
          {files.map((f, i) => (
            <div
              key={i}
              className="flex items-center gap-1.5 bg-blue-50 border border-blue-200 rounded-lg px-2.5 py-1.5 text-xs max-w-[200px]"
            >
              <span className="flex-shrink-0">{chipIcon(f.name)}</span>
              <span className="truncate text-blue-700 font-medium">{f.name}</span>
              <button
                onClick={() => removeFile(i)}
                className="flex-shrink-0 ml-0.5 text-blue-400 hover:text-blue-700 font-bold transition-colors"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="flex items-end gap-2">
        {/* 파일 첨부 버튼 */}
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={isProcessing}
          className="flex-shrink-0 p-2.5 rounded-xl text-gray-400 hover:text-blue-500 hover:bg-blue-50 disabled:opacity-40 transition-colors"
          title="파일 첨부 (xlsx·xls·csv·pdf·docx·pptx·hwp·hwpx·png·jpg) — 여러 개 선택 가능"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>
          </svg>
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept=".xlsx,.xls,.csv,.pdf,.docx,.doc,.pptx,.hwp,.hwpx,.png,.jpg,.jpeg,.webp,.gif"
          multiple
          className="hidden"
          onChange={handleFileChange}
        />

        {/* 텍스트 입력 */}
        <textarea
          ref={textareaRef}
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="질문을 입력하거나 파일을 첨부하세요… (Shift+Enter: 줄바꿈)"
          rows={1}
          disabled={isProcessing}
          className="flex-1 resize-none rounded-xl border border-gray-200 bg-gray-50 px-3.5 py-2.5 text-sm text-gray-800 placeholder:text-gray-400
            focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-400 focus:bg-white
            disabled:opacity-50 transition-all"
        />

        {/* 전송 버튼 */}
        <button
          type="button"
          onClick={handleSend}
          disabled={!canSend}
          className="flex-shrink-0 w-10 h-10 rounded-xl bg-blue-600 hover:bg-blue-700 text-white
            disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center justify-center"
        >
          {isProcessing ? (
            <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
            </svg>
          ) : (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
            </svg>
          )}
        </button>
      </div>
    </div>
  )
}
