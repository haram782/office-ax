/**
 * Date 객체를 현재 시각 기준 상대 문자열로 변환한다.
 * @param {Date} date
 * @returns {string}
 */
export function formatRelative(date) {
  const diffMin = (Date.now() - date.getTime()) / 60_000
  if (diffMin < 1)  return '방금 전'
  if (diffMin < 60) return `${Math.floor(diffMin)}분 전`
  return `${Math.floor(diffMin / 60)}시간 전`
}

/**
 * 배열을 지정한 크기 단위로 분할한다.
 * @template T
 * @param {T[]} arr
 * @param {number} size
 * @returns {T[][]}
 */
export function chunk(arr, size) {
  const result = []
  for (let i = 0; i < arr.length; i += size) {
    result.push(arr.slice(i, i + size))
  }
  return result
}

/**
 * 파이프라인 타입과 트리거 메타 정보로 목록 표시용 문자열을 생성한다.
 * @param {'A'|'B'|'C'} type
 * @param {Object} trigger_meta
 * @param {string|null} last_run_at - ISO 8601 문자열
 * @returns {string}
 */
export function buildMeta(type, trigger_meta, last_run_at) {
  let base
  if (type === 'A') base = '대화형 트리거 · 수동 실행'
  else if (type === 'B') base = `${trigger_meta?.email || '이메일'} 수신 시`
  else base = trigger_meta?.cron || '스케줄'

  if (!last_run_at) return base

  const diffMs = Date.now() - new Date(last_run_at).getTime()
  const diffH  = Math.floor(diffMs / 3_600_000)
  const diffD  = Math.floor(diffMs / 86_400_000)

  // 1시간 미만 → 방금, 24시간 미만 → N시간 전, 이상 → N일 전
  const ago = diffH < 1 ? '방금' : diffH < 24 ? `${diffH}시간 전` : `${diffD}일 전`

  return `${base} · 최근 실행 ${ago}`
}
