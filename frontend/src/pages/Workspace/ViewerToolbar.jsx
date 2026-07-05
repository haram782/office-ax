import { useState } from 'react'
import { Ic } from '../../components/Ic'

/**
 * 문서 뷰어 상단 툴바.
 * 줌·페이지 네비게이션·히스토리·다운로드 버튼을 제공한다.
 *
 * 다운로드: onDownload(선택된 버전 기준 핸들러)가 있으면 그것을 우선하고,
 * 없으면 기존 artifactUrl anchor 방식(레거시 분석 산출물)으로 폴백한다.
 */
export function ViewerToolbar({ artifactUrl, onHistoryReplay, onDownload }) {
  const [zoom, setZoom] = useState(100)

  function IconBtn({ icon, onClick, title }) {
    return (
      <button
        onClick={onClick}
        title={title}
        className="w-8 h-8 grid place-items-center rounded-lg text-zinc-500 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800"
      >
        <Ic name={icon} />
      </button>
    )
  }

  function TBtn({ icon, label, onClick, primary }) {
    const base = 'inline-flex items-center gap-1.5 rounded-lg text-xs '
    const style = primary
      ? base + 'bg-blue-600 hover:bg-blue-700 text-white font-medium px-3 py-1.5'
      : base + 'border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 hover:bg-zinc-50 dark:hover:bg-zinc-700 px-2.5 py-1.5 text-zinc-600 dark:text-zinc-300'
    return (
      <button onClick={onClick} className={style}>
        <Ic name={icon} className="w-3.5 h-3.5" />
        {label}
      </button>
    )
  }

  return (
    <div className="h-12 shrink-0 flex items-center gap-2 px-3 border-b border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900">
      {/* 패널 토글 */}
      <IconBtn icon="menu" />

      {/* 줌 컨트롤 */}
      <div className="flex items-center gap-1">
        <IconBtn icon="minus" onClick={() => setZoom(z => Math.max(25, z - 25))} />
        <span className="text-xs text-zinc-500 w-12 text-center">{zoom}%</span>
        <IconBtn icon="plus"  onClick={() => setZoom(z => Math.min(200, z + 25))} />
      </div>

      <div className="h-5 w-px bg-zinc-200 dark:bg-zinc-700 mx-1" />

      {/* 페이지 표시 */}
      <div className="flex items-center gap-1.5 text-xs text-zinc-500">
        <span className="px-2 py-0.5 rounded border border-zinc-200 dark:border-zinc-700">1</span>
        / 1
      </div>

      <IconBtn icon="rotate" title="회전" />

      <div className="flex-1" />

      {/* 히스토리 재생 */}
      {onHistoryReplay && (
        <TBtn icon="history" label="수정됨" onClick={onHistoryReplay} />
      )}

      {/* 최종본 다운로드 — 선택된 버전 핸들러 우선, 레거시 artifactUrl 폴백 */}
      {onDownload ? (
        <TBtn icon="download" label="최종본 다운로드" primary onClick={onDownload} />
      ) : artifactUrl ? (
        <a
          href={artifactUrl}
          download
          className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium px-3 py-1.5"
        >
          <Ic name="download" className="w-3.5 h-3.5" />
          최종본 다운로드
        </a>
      ) : (
        // 연결 경로가 없는 상태 — 비활성 표시로 dead button임을 드러낸다
        <button
          disabled
          className="inline-flex items-center gap-1.5 rounded-lg bg-zinc-300 dark:bg-zinc-700 text-white text-xs font-medium px-3 py-1.5 cursor-not-allowed opacity-60"
        >
          <Ic name="download" className="w-3.5 h-3.5" />
          최종본 다운로드
        </button>
      )}
    </div>
  )
}
