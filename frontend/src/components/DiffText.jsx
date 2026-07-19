import { diffSegmentsForDisplay } from '../utils/textDiff'

/**
 * original → replacement 사이에서 실제로 바뀐 부분만 취소선/하이라이트로
 * 보여준다. 공통 구간(예: 안 바뀐 라벨 텍스트)은 일반 텍스트로 그대로 표시된다.
 */
export function DiffText({ original, replacement, className = '' }) {
  const segments = diffSegmentsForDisplay(original ?? '', replacement ?? '')
  if (segments.length === 0) return null

  return (
    <span className={`truncate ${className}`} title={`${original} → ${replacement}`}>
      {segments.map((seg, i) => {
        if (seg.removed) {
          return (
            <span key={i} className="line-through text-red-400">
              {seg.value}
            </span>
          )
        }
        if (seg.added) {
          return (
            <span key={i} className="text-emerald-600 dark:text-emerald-400 font-medium">
              {seg.value}
            </span>
          )
        }
        return (
          <span key={i} className="text-zinc-500 dark:text-zinc-400">
            {seg.value}
          </span>
        )
      })}
    </span>
  )
}
