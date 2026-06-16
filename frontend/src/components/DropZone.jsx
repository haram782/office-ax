import { useState, useRef, useCallback } from 'react'
import { Spinner } from './Spinner'

const ACCEPTED_EXT = new Set(['.xlsx', '.pdf'])

function getExtension(filename) {
  return '.' + filename.split('.').pop().toLowerCase()
}

function isAccepted(file) {
  return ACCEPTED_EXT.has(getExtension(file.name))
}

export function DropZone({ onFileDrop, phase }) {
  const [isDragOver, setIsDragOver] = useState(false)
  const [rejectMsg, setRejectMsg] = useState('')
  const inputRef = useRef(null)

  const isLoading = phase === 'uploading' || phase === 'analyzing'

  const handleFile = useCallback((file) => {
    if (!isAccepted(file)) {
      setRejectMsg('Excel(.xlsx) 또는 PDF 파일만 지원합니다.')
      return
    }
    setRejectMsg('')
    onFileDrop(file)
  }, [onFileDrop])

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    setIsDragOver(false)
    const file = e.dataTransfer.files[0]
    if (file) handleFile(file)
  }, [handleFile])

  const handleDragOver = (e) => { e.preventDefault(); setIsDragOver(true) }
  const handleDragLeave = (e) => {
    // 자식 요소로 drag 이동 시 flickering 방지
    if (!e.currentTarget.contains(e.relatedTarget)) setIsDragOver(false)
  }

  const handleInputChange = (e) => {
    const file = e.target.files?.[0]
    if (file) handleFile(file)
    // 같은 파일 재업로드 허용
    e.target.value = ''
  }

  // ── 로딩 상태 ──────────────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 h-56 rounded-2xl border-2 border-blue-200 bg-blue-50/60">
        <Spinner size="lg" />
        <div className="text-center">
          <p className="text-blue-700 font-semibold animate-pulse">
            {phase === 'uploading' ? '파일 업로드 중...' : 'AI 문서 분석 중...'}
          </p>
          <p className="text-blue-400 text-sm mt-1">개인정보 자동 마스킹 후 AI에 전달됩니다</p>
        </div>
      </div>
    )
  }

  // ── 기본 드롭존 ────────────────────────────────────────────────────────────
  return (
    <div className="space-y-2">
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => e.key === 'Enter' && inputRef.current?.click()}
        aria-label="파일 업로드 영역"
        className={[
          'relative flex flex-col items-center justify-center gap-3 h-56 rounded-2xl',
          'border-2 border-dashed cursor-pointer select-none',
          'transition-all duration-150 outline-none',
          'focus-visible:ring-2 focus-visible:ring-blue-400 focus-visible:ring-offset-2',
          isDragOver
            ? 'border-blue-500 bg-blue-50 scale-[1.015]'
            : 'border-gray-300 bg-gray-50 hover:border-blue-400 hover:bg-blue-50/40',
        ].join(' ')}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".xlsx,.pdf"
          className="hidden"
          onChange={handleInputChange}
        />

        <span className={`text-5xl transition-transform duration-150 ${isDragOver ? 'scale-110' : ''}`}>
          {isDragOver ? '📂' : '📄'}
        </span>

        <div className="text-center">
          <p className="text-gray-800 font-semibold text-lg">
            {isDragOver ? '파일을 놓으세요' : '파일을 여기에 끌어다 놓으세요'}
          </p>
          <p className="text-gray-400 text-sm mt-0.5">또는 클릭해서 파일 선택</p>
        </div>

        <div className="flex gap-2">
          {['Excel  .xlsx', 'PDF  .pdf'].map((tag) => (
            <span
              key={tag}
              className="px-3 py-1 text-xs rounded-full bg-white border border-gray-200 text-gray-500 font-medium"
            >
              {tag}
            </span>
          ))}
        </div>
      </div>

      {rejectMsg && (
        <p className="text-sm text-red-500 text-center">{rejectMsg}</p>
      )}
    </div>
  )
}
