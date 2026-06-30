import { Ic } from '../../components/Ic'

// severity → 왼쪽 테두리 색상
const SEVERITY_BORDER = {
  error:   'border-l-red-400',
  warning: 'border-l-amber-400',
  info:    'border-l-zinc-300 dark:border-l-zinc-600',
}

// changeType → 한국어 레이블
const CHANGE_TYPE_LABEL = {
  correction: '교정',
  patch:      '패치',
  masking:    '마스킹',
  analysis:   '분석',
  edit:       '수정',
}

// status → 뱃지 스타일
const STATUS_BADGE = {
  pending:  { cls: 'bg-zinc-100 dark:bg-zinc-800 text-zinc-500 dark:text-zinc-400', label: '대기' },
  applied:  { cls: 'bg-emerald-50 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400', label: '적용됨' },
  rejected: { cls: 'bg-red-50 dark:bg-red-900/20 text-red-400', label: '거절됨' },
}

/**
 * anchor 객체를 짧은 위치 문자열로 변환한다.
 * 예: { type:'cell', cell:'D12', sheet:'Sheet1' } → 'D12 · Sheet1'
 */
function anchorLabel(anchor) {
  if (!anchor) return ''
  switch (anchor.type) {
    case 'cell': {
      const parts = [anchor.cell].filter(Boolean)
      if (anchor.sheet) parts.push(anchor.sheet)
      return parts.join(' · ')
    }
    case 'text_match':
      return anchor.target_text
        ? `"${anchor.target_text.slice(0, 20)}${anchor.target_text.length > 20 ? '…' : ''}"`
        : ''
    case 'slide_shape': {
      const slide = anchor.slide_index != null ? `슬라이드 ${anchor.slide_index + 1}` : ''
      const shape = anchor.shape_index != null ? `셰이프 ${anchor.shape_index + 1}` : ''
      return [slide, shape].filter(Boolean).join(', ')
    }
    default:
      return anchor.type !== 'unknown' ? anchor.type : ''
  }
}

/**
 * 개별 변경 제안 카드.
 *
 * @param {{ suggestion, status, isSelected, isPending, isAutoRejected, onSelect, onAccept, onReject, onReset }} props
 * @param {boolean} [isPending=false] - API 호출 중 여부. true이면 버튼을 비활성화한다.
 * @param {boolean} [isAutoRejected=false] - 서버가 confidence 충돌로 자동 반려한 항목인지 여부.
 */
export function ChangeSuggestionCard({ suggestion, status, isSelected, isPending = false, isAutoRejected = false, onSelect, onAccept, onReject, onReset }) {
  const { title, original, replacement, reason, anchor, changeType, severity } = suggestion

  const effectiveStatus = status ?? 'pending'
  const badge           = STATUS_BADGE[effectiveStatus] ?? STATUS_BADGE.pending
  const borderCls       = SEVERITY_BORDER[severity] ?? SEVERITY_BORDER.info
  const typeLabel       = CHANGE_TYPE_LABEL[changeType] ?? changeType ?? '변경'
  const location        = anchorLabel(anchor)

  return (
    <div
      onClick={onSelect}
      className={`
        relative cursor-pointer rounded-lg border-l-2 border border-zinc-200 dark:border-zinc-700
        bg-white dark:bg-zinc-900 p-3 transition-all select-none
        ${borderCls}
        ${isSelected
          ? 'ring-1 ring-blue-400 border-blue-300 dark:border-blue-600 shadow-sm shadow-blue-100/60 dark:shadow-blue-900/20'
          : 'hover:border-zinc-300 dark:hover:border-zinc-600 hover:shadow-sm'
        }
      `}
    >
      {/* 1행: 타입 레이블 + 상태 뱃지 */}
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <span className="text-[10px] font-semibold text-zinc-400 dark:text-zinc-500 uppercase tracking-wider">
          {typeLabel}
        </span>
        <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full ${badge.cls}`}>
          {badge.label}
        </span>
      </div>

      {/* 충돌 자동 반려 배지 — 전체 적용 시 confidence 비교로 서버가 자동 반려한 경우, 사유 전문 대신 요약만 표시 */}
      {isAutoRejected && effectiveStatus === 'rejected' && (
        <span className="inline-block text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-zinc-100 dark:bg-zinc-800 text-zinc-400 dark:text-zinc-500 mb-1.5">
          충돌로 자동 반려됨
        </span>
      )}

      {/* 2행: 제목 */}
      {title && (
        <p className="text-xs font-semibold text-zinc-700 dark:text-zinc-200 mb-1.5 leading-snug line-clamp-2">
          {title}
        </p>
      )}

      {/* 3행: original → replacement */}
      {(original || replacement) && (
        <div className="flex items-start gap-1.5 mb-1.5 text-[11px]">
          {original && (
            <span className="line-through text-red-400 truncate max-w-[80px]" title={original}>
              {original}
            </span>
          )}
          {original && replacement && (
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="flex-shrink-0 mt-0.5 text-zinc-400">
              <line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>
            </svg>
          )}
          {replacement && (
            <span className="text-emerald-600 dark:text-emerald-400 font-medium truncate max-w-[80px]" title={replacement}>
              {replacement}
            </span>
          )}
        </div>
      )}

      {/* 4행: 이유 */}
      {reason && (
        <p className="text-[10px] text-zinc-400 dark:text-zinc-500 mb-1.5 line-clamp-2 leading-relaxed">
          {reason}
        </p>
      )}

      {/* 5행: 위치 + 적용/거절 버튼 */}
      <div className="flex items-center justify-between gap-2 mt-1">
        {location ? (
          <span className="text-[10px] font-mono text-zinc-400 dark:text-zinc-500 bg-zinc-50 dark:bg-zinc-800 border border-zinc-100 dark:border-zinc-700 rounded px-1.5 py-0.5 truncate max-w-[120px]" title={location}>
            {location}
          </span>
        ) : (
          <span />
        )}

        {/* 대기 상태에만 적용/거절 버튼 표시 — API 호출 중(isPending)이면 비활성화 */}
        {effectiveStatus === 'pending' && (
          <div className="flex items-center gap-1 flex-shrink-0">
            <button
              onClick={e => { e.stopPropagation(); onReject() }}
              disabled={isPending}
              title="거절"
              className="w-6 h-6 flex items-center justify-center rounded border border-zinc-200 dark:border-zinc-700 text-zinc-400 hover:border-red-300 hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {isPending
                ? <span className="w-2.5 h-2.5 border border-zinc-400 border-t-transparent rounded-full animate-spin" />
                : <Ic name="x" className="w-3 h-3" />}
            </button>
            <button
              onClick={e => { e.stopPropagation(); onAccept() }}
              disabled={isPending}
              title="적용"
              className="w-6 h-6 flex items-center justify-center rounded border border-zinc-200 dark:border-zinc-700 text-zinc-400 hover:border-emerald-300 hover:text-emerald-500 hover:bg-emerald-50 dark:hover:bg-emerald-900/20 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {isPending
                ? <span className="w-2.5 h-2.5 border border-zinc-400 border-t-transparent rounded-full animate-spin" />
                : <Ic name="check" className="w-3 h-3" />}
            </button>
          </div>
        )}

        {/* 적용/거절 후 대기 상태로 되돌리기 */}
        {effectiveStatus !== 'pending' && (
          <button
            onClick={e => { e.stopPropagation(); onReset?.() }}
            title="대기 상태로 되돌리기"
            className="text-[10px] text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300 underline underline-offset-2 flex-shrink-0"
          >
            되돌리기
          </button>
        )}
      </div>
    </div>
  )
}
