import { useState, useEffect, useRef, useCallback } from 'react'
import { resolveViewer } from '../components/DocumentPanel'

const LS_KEY = 'ax_preview_data'

// ── Excel 뷰어 (교정 항목 플래시 지원) — 팝업 전용 ───────────────────────────

function PopupExcelViewer({ snippetData, filename, flashCells }) {
  if (!snippetData) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 text-gray-400">
        <span className="text-4xl">📊</span>
        <p className="text-sm text-center leading-relaxed">
          메인 창에서 AI 분석이 완료되면<br />
          여기에 교정 내역이 표시됩니다
        </p>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-auto p-5 space-y-5">
      {/* 원본 시트 미리보기 */}
      <div className="rounded-xl border border-gray-200 overflow-hidden shadow-sm">
        <div className="px-4 py-2.5 bg-gradient-to-r from-gray-50 to-white border-b border-gray-200 flex items-center gap-2">
          <span className="text-sm">📊</span>
          <span className="text-xs font-semibold text-gray-700">시트 미리보기</span>
          <span className="ml-auto text-[10px] text-gray-400">{filename}</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                {(snippetData.headers || []).map((h, i) => (
                  <th key={i} className="px-3 py-2 text-left font-semibold text-gray-600 whitespace-nowrap">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(snippetData.preview_rows || []).map((row, i) => (
                <tr key={i} className="border-t border-gray-100 hover:bg-blue-50/30 transition-colors">
                  {row.map((cell, j) => (
                    <td key={j} className="px-3 py-2 text-gray-700 whitespace-nowrap">
                      {typeof cell === 'number' ? cell.toLocaleString() : cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* 교정 목록 (플래시 애니메이션 적용 대상) */}
      {(snippetData.corrections || []).length > 0 && (
        <div className="rounded-xl border border-orange-100 overflow-hidden shadow-sm">
          <div className="px-4 py-2.5 bg-gradient-to-r from-orange-50 to-amber-50 border-b border-orange-100 flex items-center gap-2">
            <span className="text-sm">⚠️</span>
            <span className="text-xs font-semibold text-orange-700">
              감지 및 교정된 오류 {snippetData.corrections.length}건
            </span>
            {flashCells.size > 0 && (
              <span className="ml-auto text-[11px] text-emerald-600 font-semibold animate-pulse">
                ✨ AI 수정 사항 반영됨
              </span>
            )}
          </div>
          <div className="divide-y divide-orange-50">
            {snippetData.corrections.map((c, i) => {
              const isFlashing = flashCells.has(c.cell)
              return (
                <div
                  key={`${c.cell}-${i}`}
                  className={`px-4 py-3 flex items-center gap-3 ${isFlashing ? 'animate-flash-highlight' : ''}`}
                >
                  <span className="font-mono text-xs font-bold text-gray-500 w-10 flex-shrink-0 bg-gray-100 rounded px-1.5 py-0.5 text-center">
                    {c.cell}
                  </span>
                  <div className="flex-1 flex items-center gap-2 min-w-0 text-xs">
                    <span className="text-red-400 line-through truncate">{c.original}</span>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="flex-shrink-0 text-gray-400">
                      <line x1="5" y1="12" x2="19" y2="12"/>
                      <polyline points="12 5 19 12 12 19"/>
                    </svg>
                    <span className="text-emerald-600 font-semibold truncate">{c.corrected}</span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

// ── PDF 뷰어 ──────────────────────────────────────────────────────────────────

function PopupPdfViewer({ fileUrl, filename }) {
  if (!fileUrl) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 text-gray-400">
        <span className="text-4xl">📄</span>
        <p className="text-sm text-center leading-relaxed">PDF 미리보기를 준비 중입니다…</p>
      </div>
    )
  }
  return (
    <iframe
      src={fileUrl}
      title={`PDF 미리보기: ${filename}`}
      className="w-full border-0"
      style={{ flex: '1 1 0px', minHeight: 0 }}
    />
  )
}

// ── 메인 팝업 페이지 ──────────────────────────────────────────────────────────

export default function PreviewPage() {
  // localStorage에서 초기 데이터 읽기 (팝업 오픈 시점)
  const [data, setData] = useState(() => {
    try {
      const raw = localStorage.getItem(LS_KEY)
      return raw ? JSON.parse(raw) : null
    } catch {
      return null
    }
  })

  // 플래시 대상 셀 집합 (Set<string>: c.cell 값들)
  const [flashCells, setFlashCells] = useState(new Set())
  const timeoutsRef = useRef([])

  const triggerFlash = useCallback((cells) => {
    if (!cells?.length) return

    // 이전 타임아웃 전부 해제 (메모리 누수 방지)
    timeoutsRef.current.forEach(clearTimeout)
    timeoutsRef.current = []

    setFlashCells(new Set(cells))

    const t = setTimeout(() => {
      setFlashCells(new Set())
    }, 2000)
    timeoutsRef.current.push(t)
  }, [])

  // 메인 창 → 팝업 실시간 동기화 (storage 이벤트: 다른 탭/창에서만 발생)
  useEffect(() => {
    const handler = (e) => {
      if (e.key !== LS_KEY || !e.newValue) return
      try {
        const parsed = JSON.parse(e.newValue)
        setData(parsed)
        if (parsed.highlightedCells?.length > 0) {
          triggerFlash(parsed.highlightedCells)
        }
      } catch {
        // 파싱 실패 시 무시
      }
    }

    window.addEventListener('storage', handler)
    return () => window.removeEventListener('storage', handler)
  }, [triggerFlash])

  // 언마운트 시 남은 타임아웃 정리
  useEffect(() => {
    return () => {
      timeoutsRef.current.forEach(clearTimeout)
    }
  }, [])

  const filename = data?.filename ?? ''
  const isExcel = filename.toLowerCase().endsWith('.xlsx') || filename.toLowerCase().endsWith('.xls')

  // 팝업 본문 렌더링:
  // Excel은 flashCells가 필요하므로 팝업 전용 PopupExcelViewer 사용.
  // 그 외 포맷은 resolveViewer()에 위임(DocumentPanel과 동일 로직).
  function renderBody() {
    if (!data) {
      return (
        <div className="flex flex-col items-center justify-center h-full gap-4 text-gray-400">
          <div className="w-14 h-14 rounded-2xl bg-gray-100 flex items-center justify-center text-3xl">
            📂
          </div>
          <div className="text-center space-y-1">
            <p className="text-sm font-medium text-gray-500">데이터를 기다리는 중입니다</p>
            <p className="text-xs leading-relaxed">
              메인 창의 뷰어에서<br />'새 창' 버튼을 다시 눌러주세요
            </p>
          </div>
        </div>
      )
    }

    if (isExcel) {
      return (
        <PopupExcelViewer
          snippetData={data.snippetData}
          filename={filename}
          flashCells={flashCells}
        />
      )
    }

    // 그 외: resolveViewer() — DocumentPanel과 동일한 switch 분기
    return resolveViewer({ filename, fileUrl: data.fileUrl, snippetData: data.snippetData })
  }

  return (
    <div className="h-screen flex flex-col bg-white">
      {/* 헤더 */}
      <header className="flex-shrink-0 h-11 border-b border-gray-200 bg-white/95 backdrop-blur flex items-center px-4 gap-3">
        <div className="w-6 h-6 rounded-md bg-blue-600 flex items-center justify-center text-white text-[10px] font-black shadow shadow-blue-200">
          AX
        </div>
        <span className="text-xs font-semibold text-gray-700 truncate flex-1 min-w-0" title={filename}>
          {filename || '문서 미리보기'}
        </span>

        {/* 보정 파일 다운로드 */}
        {data?.artifactUrl && (
          <a
            href={data.artifactUrl}
            download
            className="flex-shrink-0 flex items-center gap-1 text-[11px] text-emerald-600 hover:text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-2.5 py-1.5 transition-colors"
          >
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="7 10 12 15 17 10"/>
              <line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
            보정 파일
          </a>
        )}

        <button
          onClick={() => window.close()}
          className="flex-shrink-0 text-xs text-gray-400 hover:text-gray-600 border border-gray-200 hover:border-gray-300 rounded-lg px-3 py-1.5 transition-colors"
        >
          닫기
        </button>
      </header>

      {/* 본문 */}
      <div className="flex-1 overflow-hidden flex flex-col min-h-0">
        {renderBody()}
      </div>
    </div>
  )
}
