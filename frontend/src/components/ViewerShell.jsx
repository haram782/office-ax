import { useState } from 'react'
import { Ic } from './Ic'
import { ViewerToolbar } from '../pages/Workspace/ViewerToolbar'

/**
 * 뷰어 공통 셸 컴포넌트.
 * WorkspaceCenter와 PreviewPage가 공유하는 헤더 + 툴바 + 뷰어/패널 레이아웃을 제공한다.
 *
 * @param {{
 *   filename:     string,
 *   artifactUrl:  string | null,
 *   onClose:      (() => void) | null,
 *   onNewWindow:  (() => void) | null,
 *   sidePanel:    ReactNode | null,
 *   inputPanel:   ReactNode | null,
 *   children:     ReactNode,
 *   headerExtra:  ReactNode | null,
 *   versionPanel: ReactNode | null,
 *   banner:       ReactNode | null,
 *   className:    string,
 * }} props
 */
export function ViewerShell({
  filename,
  artifactUrl  = null,
  onDownload   = null,
  onClose      = null,
  onNewWindow  = null,
  sidePanel    = null,
  inputPanel   = null,
  children,
  headerExtra  = null,
  versionPanel = null,
  banner       = null,
  className    = 'flex-1 min-w-0 flex flex-col relative bg-zinc-50 dark:bg-zinc-950',
}) {
  // 뷰어 줌 — 툴바가 제어하고 셸이 콘텐츠에 scale로 반영한다 (A-4: 장식이던 줌을 실동작으로)
  const [zoom, setZoom] = useState(100)

  return (
    <div className={className}>
      {/* 파일명 헤더 — 전체 너비 */}
      <div className="h-11 shrink-0 flex items-center justify-between px-4 border-b border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900">
        {/* 좌측: headerExtra(로고 등) + 파일명 */}
        <div className="flex items-center gap-2 min-w-0">
          {headerExtra}
          <span className="text-sm text-zinc-700 dark:text-zinc-200 truncate" title={filename}>
            {filename || '문서 미리보기'}
          </span>
        </div>

        {/* 우측: 새 창 버튼(선택) + 닫기 버튼(선택) */}
        <div className="flex items-center gap-1 flex-shrink-0">
          {onNewWindow && (
            <button
              onClick={onNewWindow}
              className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 hover:bg-zinc-50 dark:hover:bg-zinc-700 text-xs px-2.5 py-1.5 text-zinc-600 dark:text-zinc-300"
            >
              <Ic name="externalLink" className="w-3.5 h-3.5" />
              새 창
            </button>
          )}
          {onClose && (
            <button
              aria-label="닫기"
              onClick={onClose}
              className="w-11 h-11 min-w-[44px] min-h-[44px] grid place-items-center rounded-lg text-zinc-500 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800"
            >
              <Ic name="x" />
            </button>
          )}
        </div>
      </div>

      {/* 뷰어 툴바 — 다운로드 / 줌 / 히스토리 */}
      <ViewerToolbar artifactUrl={artifactUrl} onDownload={onDownload} zoom={zoom} onZoomChange={setZoom} />

      {versionPanel}

      {/* 콘텐츠 영역: 뷰어(좌) + 사이드 패널(우) */}
      <div className="flex-1 min-h-0 overflow-hidden flex flex-row">
        <div className="flex-1 min-w-0 min-h-0 overflow-auto flex flex-col">
          {/* 줌 래퍼 — 100%가 아닐 때만 scale 적용 (기본 상태에서 레이아웃 영향 없음) */}
          <div
            data-testid="viewer-zoom-wrapper"
            className="flex-1 min-h-0 flex flex-col"
            style={zoom === 100 ? undefined : { transform: `scale(${zoom / 100})`, transformOrigin: 'top center' }}
          >
            {children}
          </div>
          {/* 뷰어 하단 입력 슬롯 (수정 요청 입력창 등) */}
          {inputPanel}
        </div>
        {sidePanel}
      </div>

      {/* 오버레이 배너 슬롯 (AutomationBanner 등) */}
      {banner}
    </div>
  )
}
