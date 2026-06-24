import { Ic } from '../../components/Ic'
import { resolveViewer } from '../../components/DocumentPanel'

/**
 * 범용 파일 뷰어 모달.
 * 이메일 첨부 · RAG 문서 · 워크스페이스 팝업 모두 이 컴포넌트를 재사용한다.
 *
 * @param {{
 *   filename: string,
 *   fileUrl?: string,
 *   snippetData?: object,
 *   title?: string,
 *   onClose: () => void,
 * }} props
 */
export function SubViewerPopup({ filename, fileUrl, snippetData, title, onClose }) {
  // /preview 페이지는 localStorage의 ax_preview_data를 읽어 파일을 렌더링한다
  const handleOpenNewTab = () => {
    localStorage.setItem('ax_preview_data', JSON.stringify({
      filename,
      fileUrl:          fileUrl ?? '',
      artifactUrl:      '',
      snippetData:      snippetData ?? null,
      highlightedCells: [],
      updateId:         Date.now(),
    }))
    window.open('/preview', '_blank')
    onClose()
  }

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/40 backdrop-blur-sm animate-fade-in"
      onClick={onClose}
    >
      <div
        onClick={e => e.stopPropagation()}
        className="w-[640px] max-h-[80vh] flex flex-col rounded-xl bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 shadow-2xl overflow-hidden"
      >
        {/* 헤더: 파일명(좌) + [새 탭 버튼 + 닫기 버튼](우) */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-200 dark:border-zinc-800">
          <div className="flex items-center gap-2 text-sm font-medium text-zinc-700 dark:text-zinc-200 min-w-0">
            <Ic name="fileText" className="w-4 h-4 text-blue-600 shrink-0" />
            <span className="truncate">{title ?? filename}</span>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <button
              onClick={handleOpenNewTab}
              title="새 탭으로 열기"
              className="shrink-0 w-7 h-7 grid place-items-center rounded-lg text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800"
            >
              <Ic name="externalLink" className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={onClose}
              className="shrink-0 w-7 h-7 grid place-items-center rounded-lg text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800"
            >
              <Ic name="x" />
            </button>
          </div>
        </div>

        {/* 뷰어 본문 */}
        <div className="flex-1 min-h-0 overflow-hidden flex flex-col">
          {resolveViewer({ filename, fileUrl, snippetData })}
        </div>
      </div>
    </div>
  )
}
