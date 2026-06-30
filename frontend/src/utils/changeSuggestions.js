/**
 * snippetData의 다양한 분석 결과 포맷을 공통 suggestion 배열로 정규화한다.
 * 원본 객체를 mutate하지 않는다.
 *
 * 우선순위: patch_changes > edit_suggestions > change_highlights > corrections
 * 동일 anchor를 가진 항목은 높은 우선순위 항목만 유지한다.
 * patch_changes만 서버 DocumentChange PK(changeDbId)를 가지므로 항상 최우선이다.
 */

// ── 내부 유틸 ──────────────────────────────────────────────────────────────────

/** snippetData.type → format 문자열 매핑 */
const TYPE_FORMAT_MAP = {
  excel_preview: 'xlsx',
  pptx_preview:  'pptx',
  docx_pages:    'docx',
}

/**
 * snippetData에서 포맷 문자열을 유추한다.
 * snippetData.format > TYPE_FORMAT_MAP[type] > 'unknown' 순으로 폴백.
 */
function _inferFormat(snippetData) {
  if (snippetData.format) return snippetData.format
  return TYPE_FORMAT_MAP[snippetData.type] ?? 'unknown'
}

/**
 * anchor 객체 → 중복 제거용 키 문자열.
 * null 반환 시 해당 항목은 중복 제거 대상이 아니다 (항상 추가).
 */
function _anchorKey(anchor) {
  if (!anchor) return null
  switch (anchor.type) {
    case 'cell':
      // 셀 주소(시트 포함)가 같으면 동일 항목으로 간주
      return `cell:${anchor.sheet ?? ''}:${anchor.cell ?? ''}`
    case 'text_match':
      return `text:${anchor.target_text ?? ''}`
    case 'slide_shape':
      // 슬라이드·셰이프 조합으로 동일 위치 판별
      return `shape:${anchor.slide_index ?? ''}:${anchor.shape_index ?? ''}:${anchor.row_index ?? ''}:${anchor.col_index ?? ''}`
    default:
      // 알 수 없는 anchor 타입은 중복 판별 불가 → 항상 추가
      return null
  }
}

/** change_highlights.target → anchor 객체 변환 */
function _highlightToAnchor(h) {
  const target = h.target ?? ''

  if (target === 'cell') {
    return { type: 'cell', cell: h.cell ?? '', sheet: h.sheet ?? '' }
  }
  if (target === 'text') {
    return {
      type:           'text_match',
      target_text:    h.target_text    ?? '',
      context_before: h.context_before ?? '',
      context_after:  h.context_after  ?? '',
    }
  }
  if (target === 'shape' || target === 'table_cell') {
    return {
      type:        'slide_shape',
      slide_index: h.slide_index ?? null,
      shape_index: h.shape_index ?? null,
      row_index:   h.row_index   ?? null,
      col_index:   h.col_index   ?? null,
    }
  }
  // slide, page 등 위치 정보 없는 target
  return { type: target || 'unknown' }
}

// ── 소스별 변환 함수 ────────────────────────────────────────────────────────────

/**
 * patch_changes 항목 → suggestion.
 * BE의 DocumentChange 모델을 직접 반영하므로 changeDbId = id이다.
 */
function _fromPatchChange(c, index, inferredFormat) {
  return {
    id:          c.operation_id                 ?? `patch-${index}`,
    source:      'patch_changes',
    format:      c.format                       ?? inferredFormat,
    target:      c.target                       ?? 'unknown',
    changeType:  c.changeType   ?? c.kind       ?? 'patch',
    severity:    c.severity                     ?? 'info',
    status:      c.status                       ?? 'pending',
    title:       c.title        ?? c.summary    ?? '',
    original:    c.original                     ?? '',
    replacement: c.replacement  ?? c.corrected  ?? '',
    reason:      c.reason       ?? c.summary    ?? '',
    anchor:      c.anchor                       ?? { type: 'unknown' },
    // patch_changes는 항상 BE의 DocumentChange PK를 id 필드로 가진다
    changeDbId:  c.id                           ?? null,
  }
}

/** corrections 항목 → suggestion */
function _fromCorrection(c, index, inferredFormat) {
  return {
    id:          c.id                         ?? `correction-${index}`,
    source:      'corrections',
    format:      c.format                     ?? inferredFormat,
    target:      'cell',
    changeType:  'correction',
    severity:    c.severity                   ?? 'info',
    status:      c.status                     ?? 'pending',
    title:       c.summary     || c.corrected || '',
    original:    c.original                   ?? '',
    replacement: c.corrected   ?? c.replacement ?? '',
    reason:      c.summary     ?? c.reason    ?? '',
    anchor:      { type: 'cell', cell: c.cell ?? '', sheet: c.sheet ?? '' },
    // BE가 DocumentChange PK를 제공하면 패스스루 (없으면 null → 로컬 상태 전용)
    changeDbId:  c.changeDbId                 ?? null,
  }
}

/** change_highlights 항목 → suggestion */
function _fromChangeHighlight(h, index, inferredFormat) {
  return {
    id:          h.id                          ?? `highlight-${index}`,
    source:      'change_highlights',
    format:      h.format                      ?? inferredFormat,
    target:      h.target                      ?? 'unknown',
    changeType:  h.kind                        ?? 'unknown',
    severity:    h.severity                    ?? 'info',
    status:      h.status                      ?? 'pending',
    title:       h.summary     || h.corrected  || '',
    original:    h.original                    ?? '',
    replacement: h.corrected   ?? h.replacement ?? '',
    reason:      h.summary     ?? h.reason     ?? '',
    anchor:      _highlightToAnchor(h),
    changeDbId:  h.changeDbId                  ?? null,
  }
}

/**
 * edit_suggestions 항목 → suggestion.
 * edit_suggestions는 이미 표준 shape에 가까운 형태를 가정하되,
 * 누락 필드는 change_highlights 호환 필드(kind, corrected, summary)로 폴백한다.
 */
function _fromEditSuggestion(s, index, inferredFormat) {
  return {
    id:          s.id                          ?? `edit-${index}`,
    source:      'edit_suggestions',
    format:      s.format                      ?? inferredFormat,
    target:      s.target                      ?? 'unknown',
    changeType:  s.changeType  ?? s.kind       ?? 'edit',
    severity:    s.severity                    ?? 'info',
    status:      s.status                      ?? 'pending',
    title:       s.title       ?? s.summary    ?? '',
    original:    s.original                    ?? '',
    replacement: s.replacement ?? s.corrected  ?? '',
    reason:      s.reason      ?? s.summary    ?? '',
    anchor:      s.anchor                      ?? { type: 'unknown' },
    changeDbId:  s.changeDbId                  ?? null,
  }
}

// ── 공개 API ────────────────────────────────────────────────────────────────────

/**
 * snippetData를 공통 suggestion 배열로 정규화한다.
 *
 * @param {object|null} snippetData
 * @param {object}      [opts]
 * @param {string}      [opts.format] - 파일 포맷 힌트 (xlsx, csv, pptx, ...).
 *                                      snippetData.type 유추보다 우선 적용된다.
 * @returns {Array<object>}
 */
export function deriveChangeSuggestions(snippetData, { format } = {}) {
  if (!snippetData) return []

  const inferredFormat = format ?? _inferFormat(snippetData)

  // 원본 배열을 직접 순회만 하고 수정하지 않는다
  const editSuggestions  = Array.isArray(snippetData.edit_suggestions)  ? snippetData.edit_suggestions  : []
  const changeHighlights = Array.isArray(snippetData.change_highlights) ? snippetData.change_highlights : []
  const corrections      = Array.isArray(snippetData.corrections)       ? snippetData.corrections       : []
  const patchChanges     = Array.isArray(snippetData.patch_changes)     ? snippetData.patch_changes     : []

  // anchorKey → true: 이미 추가된 anchor 추적 (null key는 관리 안 함)
  const seen   = new Map()
  const result = []

  // 1순위: patch_changes — 서버 DocumentChange PK(changeDbId)를 가진 유일한 소스.
  // patch plan 생성 이후에는 서버가 source of truth이므로 다른 소스보다 항상 우선한다.
  for (const [i, c] of patchChanges.entries()) {
    const suggestion = _fromPatchChange(c, i, inferredFormat)
    const key = _anchorKey(suggestion.anchor)
    if (key !== null) seen.set(key, true)
    result.push(suggestion)
  }

  // 2순위: edit_suggestions — patch_changes와 중복 anchor 제거
  for (const [i, s] of editSuggestions.entries()) {
    const suggestion = _fromEditSuggestion(s, i, inferredFormat)
    const key = _anchorKey(suggestion.anchor)
    if (key !== null && seen.has(key)) continue
    if (key !== null) seen.set(key, true)
    result.push(suggestion)
  }

  // 3순위: change_highlights — 위 소스들과 중복 anchor 제거
  for (const [i, h] of changeHighlights.entries()) {
    const suggestion = _fromChangeHighlight(h, i, inferredFormat)
    const key = _anchorKey(suggestion.anchor)
    if (key !== null && seen.has(key)) continue
    if (key !== null) seen.set(key, true)
    result.push(suggestion)
  }

  // 4순위: corrections — 위 소스들과 중복 anchor 제거
  for (const [i, c] of corrections.entries()) {
    const suggestion = _fromCorrection(c, i, inferredFormat)
    const key = _anchorKey(suggestion.anchor)
    if (key !== null && seen.has(key)) continue
    if (key !== null) seen.set(key, true)
    result.push(suggestion)
  }

  return result
}

/**
 * suggestions 배열로 초기 statuses 맵을 생성한다.
 * 구버전 'accepted'는 'applied'로 normalize한다.
 *
 * @param {Array} suggestions
 * @returns {{ [id: string]: 'pending' | 'applied' | 'rejected' }}
 */
export function buildInitialStatuses(suggestions) {
  const map = {}
  for (const s of suggestions) {
    const raw = s.status ?? 'pending'
    map[s.id] = raw === 'accepted' ? 'applied' : raw
  }
  return map
}
