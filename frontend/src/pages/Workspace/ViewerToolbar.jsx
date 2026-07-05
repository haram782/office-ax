import { Ic } from '../../components/Ic'

// 컴포넌트 밖 정의 — 렌더마다 타입이 바뀌어 재마운트(포커스·이벤트 유실)되는 것을 방지한다
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

/**
 * 문서 뷰어 상단 툴바 — 줌·히스토리·다운로드.
 *
 * 줌은 controlled — ViewerShell이 state를 소유하고 콘텐츠에 scale로 반영한다.
 * 다운로드는 onDownload(선택된 버전 기준 핸들러)가 있으면 우선하고,
 * 없으면 기존 artifactUrl anchor 방식(레거시 분석 산출물)으로 폴백한다.
 * 동작 없던 장식 컨트롤(메뉴·회전·페이지 표시)은 제거했다 (점검 발견 A-4).
 */
export function ViewerToolbar({ artifactUrl, onHistoryReplay, onDownload, zoom = 100, onZoomChange = null }) {
  return (
    <div className="h-12 shrink-0 flex items-center gap-2 px-3 border-b border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900">
      {/* 줌 컨트롤 */}
      <div className="flex items-center gap-1">
        <IconBtn icon="minus" onClick={() => onZoomChange?.(Math.max(25, zoom - 25))} />
        <span className="text-xs text-zinc-500 w-12 text-center">{zoom}%</span>
        <IconBtn icon="plus"  onClick={() => onZoomChange?.(Math.min(200, zoom + 25))} />
      </div>

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
