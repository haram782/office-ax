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

// set_cell_style patch 필드 → 한국어 레이블 (document-format-editing-ax-v1-ko.md 9.2절 표시 예시 기준)
const STYLE_HORIZONTAL_ALIGN_LABEL = { left: '왼쪽 정렬', center: '가운데 정렬', right: '오른쪽 정렬' }
const STYLE_VERTICAL_ALIGN_LABEL   = { top: '위쪽 정렬', center: '세로 가운데 정렬', bottom: '아래쪽 정렬' }
const STYLE_BORDER_LABEL           = { thin: '얇은 테두리', medium: '중간 테두리', none: '테두리 없음' }

/**
 * set_cell_style patch(whitelist 필드)를 "굵게 · 배경색 D9EAF7 · 가운데 정렬 · 얇은 테두리" 형태로 요약한다.
 * 필드가 하나도 없으면 빈 문자열을 반환한다.
 */
function styleSummaryLabel(patch) {
  if (!patch) return ''
  const parts = []
  if (patch.font_bold === true) parts.push('굵게')
  if (patch.font_bold === false) parts.push('굵기 해제')
  if (patch.fill_color) parts.push(`배경색 ${patch.fill_color}`)
  if (patch.horizontal_alignment) {
    parts.push(STYLE_HORIZONTAL_ALIGN_LABEL[patch.horizontal_alignment] ?? patch.horizontal_alignment)
  }
  if (patch.vertical_alignment) {
    parts.push(STYLE_VERTICAL_ALIGN_LABEL[patch.vertical_alignment] ?? patch.vertical_alignment)
  }
  if (patch.border) parts.push(STYLE_BORDER_LABEL[patch.border] ?? patch.border)
  return parts.join(' · ')
}

/**
 * set_number_format patch를 "표시 형식 #,##0원로 변경" 형태로 요약한다.
 * number_format이 없으면 빈 문자열을 반환한다.
 */
function numberFormatSummaryLabel(patch) {
  if (!patch || !patch.number_format) return ''
  return `표시 형식 ${patch.number_format}로 변경`
}

/**
 * set_formula patch를 "수식 =SUM(D2:D10) 설정" 형태로 요약한다.
 * formula가 없으면 빈 문자열을 반환한다.
 */
function formulaSummaryLabel(patch) {
  if (!patch || !patch.formula) return ''
  return `수식 ${patch.formula} 설정`
}

// operation → summary label 함수 매핑. original/replacement diff 대신 요약 문장을 보여주는
// operation 집합이다 (roadmap v1 8절 UX 방향: operation별 표시 방식).
const SUMMARY_LABEL_BY_OPERATION = {
  set_cell_style:     styleSummaryLabel,
  set_number_format:  numberFormatSummaryLabel,
  set_formula:        formulaSummaryLabel,
}

// status → 뱃지 스타일
const STATUS_BADGE = {
  pending:    { cls: 'bg-zinc-100 dark:bg-zinc-800 text-zinc-500 dark:text-zinc-400', label: '대기' },
  accepted:   { cls: 'bg-blue-50 dark:bg-blue-900/25 text-blue-600 dark:text-blue-400', label: '생성 대기' },
  generating: { cls: 'bg-blue-50 dark:bg-blue-900/25 text-blue-600 dark:text-blue-400', label: '생성 중' },
  applied:    { cls: 'bg-emerald-50 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400', label: '반영됨' },
  failed:     { cls: 'bg-red-50 dark:bg-red-900/20 text-red-500', label: '생성 실패' },
  rejected:   { cls: 'bg-red-50 dark:bg-red-900/20 text-red-400', label: '거절됨' },
  // BE AnchorResolver가 후보를 여러 개 찾아 자동 반영을 멈춘 상태(needs_confirmation) —
  // "실패"가 아니라 "위치를 특정하지 못해 확인이 필요함"을 구분해서 보여준다.
  needs_confirmation: { cls: 'bg-amber-50 dark:bg-amber-900/20 text-amber-600 dark:text-amber-400', label: '위치 확인 필요' },
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
    case 'cell_range': {
      const parts = [anchor.range].filter(Boolean)
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
 * @param {{ suggestion, status, isSelected, isPending, isAutoRejected, canEdit, canReset, onSelect, onAccept, onReject, onReset }} props
 * @param {boolean} [isPending=false] - API 호출 중 여부. true이면 버튼을 비활성화한다.
 * @param {boolean} [isAutoRejected=false] - 서버가 confidence 충돌로 자동 반려한 항목인지 여부.
 */
export function ChangeSuggestionCard({
  suggestion,
  status,
  isSelected,
  isPending = false,
  isAutoRejected = false,
  canEdit = true,
  canReset = true,
  onSelect,
  onAccept,
  onReject,
  onReset,
}) {
  const {
    title,
    original,
    replacement,
    reason,
    anchor,
    changeType,
    severity,
    operation,
    patch,
    failureMessage,
  } = suggestion

  const effectiveStatus = status ?? 'pending'
  const badge           = STATUS_BADGE[effectiveStatus] ?? STATUS_BADGE.pending
  const borderCls       = SEVERITY_BORDER[severity] ?? SEVERITY_BORDER.info
  const typeLabel       = CHANGE_TYPE_LABEL[changeType] ?? changeType ?? '변경'
  const location        = anchorLabel(anchor)

  // set_cell_style/set_number_format/set_formula는 original/replacement가 비어 있는
  // operation summary 타입이므로 빈 diff를 보여주지 않고 패치 내용을 요약 문장으로
  // 표시한다 (9.2절, document-editing-ax-next-roadmap-v1-ko.md 8절).
  const summaryLabelFn = SUMMARY_LABEL_BY_OPERATION[operation]
  const isStyleChange  = summaryLabelFn != null
  const styleSummary   = isStyleChange ? summaryLabelFn(patch) : ''

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

      {/* 3행: set_cell_style은 스타일 요약, 그 외는 original → replacement diff */}
      {isStyleChange ? (
        styleSummary && (
          <p className="text-[11px] text-zinc-600 dark:text-zinc-300 mb-1.5 leading-relaxed">
            {styleSummary}
          </p>
        )
      ) : (
        (original || replacement) && (
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
        )
      )}

      {/* 4행: 이유 */}
      {reason && (
        <p className="text-[10px] text-zinc-400 dark:text-zinc-500 mb-1.5 line-clamp-2 leading-relaxed">
          {reason}
        </p>
      )}

      {failureMessage && ['failed', 'needs_confirmation'].includes(effectiveStatus) && (
        <p
          role={effectiveStatus === 'failed' ? 'alert' : 'status'}
          className={`mb-1.5 rounded px-2 py-1.5 text-[11px] leading-relaxed ${
            effectiveStatus === 'failed'
              ? 'bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-300'
              : 'bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300'
          }`}
        >
          {failureMessage}
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
        {canEdit && effectiveStatus === 'pending' && (
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
        {canReset && effectiveStatus !== 'pending' && (
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
