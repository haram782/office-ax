import { Ic } from '../../components/Ic'
import { resolveViewer } from '../../components/DocumentPanel'
import { ViewerToolbar }   from './ViewerToolbar'
import { AutomationBanner } from './AutomationBanner'

/**
 * 워크스페이스 중앙 문서 뷰어 영역.
 * 파일이 선택된 경우 resolveViewer()로 뷰어를 렌더한다.
 * 선택된 파일이 없으면 안내 메시지를 보여준다.
 */
export function WorkspaceCenter({
  previewData,
  onCloseViewer,
  showBanner,
  onDismissBanner,
}) {
  // 파일 미선택 상태
  if (!previewData) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center bg-zinc-100 dark:bg-zinc-950 text-zinc-400">
        <Ic name="fileText" className="w-10 h-10 mb-3 opacity-20" />
        <p className="text-sm">좌측에서 파일을 선택하면 문서가 표시됩니다</p>
      </div>
    )
  }

  const { filename, artifactUrl } = previewData

  return (
    /* 뷰어 패널 — 고정폭 420px, 채팅과 사이드바 사이 중앙에 위치 */
    /* 뷰어 패널 — 중앙에서 가장 넓은 영역 차지 */
    <div className="flex-1 min-w-0 flex flex-col relative bg-zinc-50 dark:bg-zinc-950 border-r border-zinc-200 dark:border-zinc-800">
      {/* 파일명 헤더 */}
      <div className="h-11 shrink-0 flex items-center justify-between px-4 border-b border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900">
        <div className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-200">
          <Ic name="fileText" className="w-4 h-4 text-zinc-400" />
          {filename}
        </div>
        <div className="flex items-center gap-1">
          {/* 새 탭 열기 — localStorage에 previewData 저장 후 /preview 탭 열기 */}
          <button
            onClick={() => {
              localStorage.setItem('ax_preview_data', JSON.stringify(previewData))
              window.open('/preview', '_blank')
            }}
            className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 hover:bg-zinc-50 dark:hover:bg-zinc-700 text-xs px-2.5 py-1.5 text-zinc-600 dark:text-zinc-300"
          >
            <Ic name="externalLink" className="w-3.5 h-3.5" />
            새 창
          </button>
          {/* 뷰어 닫기 */}
          <button
            onClick={onCloseViewer}
            className="w-11 h-11 min-w-[44px] min-h-[44px] grid place-items-center rounded-lg text-zinc-500 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800"
          >
            <Ic name="x" />
          </button>
        </div>
      </div>

      {/* 뷰어 툴바 */}
      <ViewerToolbar artifactUrl={artifactUrl} />

      {/* 실제 문서 뷰어 — resolveViewer가 자체 스크롤/패딩 담당 */}
      <div className="flex-1 min-h-0 overflow-hidden flex flex-col">
        {resolveViewer(previewData)}
      </div>

      {/* 자동화 감지 배너 */}
      {showBanner && <AutomationBanner onDismiss={onDismissBanner} />}
    </div>
  )
}
