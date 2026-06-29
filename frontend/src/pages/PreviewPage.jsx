import { useState, useEffect } from 'react'
import { resolveViewer }         from '../components/DocumentPanel'
import { ViewerShell }           from '../components/ViewerShell'
import { useChangeSuggestions }  from '../hooks/useChangeSuggestions'
import { ChangeSuggestionPanel } from './Workspace/ChangeSuggestionPanel'

const LS_KEY = 'ax_preview_data'

// ── AX 로고 배지 — PreviewPage 헤더 좌측 ───────────────────────────────────────
const AX_LOGO = (
  <div className="w-6 h-6 rounded-md bg-blue-600 flex items-center justify-center text-white text-[10px] font-black shadow shadow-blue-200 flex-shrink-0">
    AX
  </div>
)

// ── 메인 팝업 페이지 ──────────────────────────────────────────────────────────

export default function PreviewPage() {
  // localStorage에서 초기 previewData 읽기
  const [previewData, setPreviewData] = useState(() => {
    try {
      const raw = localStorage.getItem(LS_KEY)
      return raw ? JSON.parse(raw) : null
    } catch {
      return null
    }
  })

  const {
    suggestions,
    statuses,
    selectedSuggestionId,
    setSelectedSuggestionId,
    highlights,
    pendingIds,
    handleSetStatus,
    handleAcceptAll,
    handleSelectHighlight,
  } = useChangeSuggestions(previewData?.snippetData ?? null)

  // 메인 창 → 팝업 실시간 동기화 (storage 이벤트는 다른 탭/창에서만 발생)
  useEffect(() => {
    const handler = (e) => {
      if (e.key !== LS_KEY || !e.newValue) return
      try {
        setPreviewData(JSON.parse(e.newValue))
      } catch {
        // 파싱 실패 시 무시
      }
    }
    window.addEventListener('storage', handler)
    return () => window.removeEventListener('storage', handler)
  }, [])

  // ViewerShell의 children: previewData 없으면 빈 상태 안내 표시
  const viewerContent = !previewData ? (
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
  ) : (
    resolveViewer(previewData, {
      highlights,
      selectedHighlightId:  selectedSuggestionId,
      onSelectHighlight:    handleSelectHighlight,
    })
  )

  return (
    <ViewerShell
      className="h-screen flex flex-col bg-white"
      filename={previewData?.filename ?? ''}
      artifactUrl={previewData?.artifactUrl ?? null}
      onClose={() => window.close()}
      onNewWindow={null}
      headerExtra={AX_LOGO}
      sidePanel={
        suggestions.length > 0 ? (
          <ChangeSuggestionPanel
            suggestions={suggestions}
            statuses={statuses}
            pendingIds={pendingIds}
            onSetStatus={handleSetStatus}
            onAcceptAll={handleAcceptAll}
            selectedSuggestionId={selectedSuggestionId}
            onSelectSuggestion={setSelectedSuggestionId}
          />
        ) : null
      }
    >
      {viewerContent}
    </ViewerShell>
  )
}
