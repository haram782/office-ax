// 시트당 렌더링 상한 — 비정상적으로 큰 시트가 브라우저 탭을 멈추지 않도록 하는 안전장치.
// 실사용 미리보기 문서 규모(수십~수백 행)를 넉넉히 덮는다.
const MAX_RENDER_ROWS = 500
const MAX_RENDER_COLS = 60

/**
 * SheetJS worksheet를 병합 셀을 반영한 렌더 그리드로 변환한다.
 *
 * row/col은 워크시트의 실제(절대, 0-based) 좌표를 그대로 유지한다 — 백엔드
 * patcher(backend/apps/documents/patcher.py)가 anchor.cell을 openpyxl A1
 * 표기로 그대로 해석하므로, 프론트 렌더 좌표도 동일한 절대 좌표계를 써야
 * 하이라이트 매칭이 어긋나지 않는다.
 *
 * 병합 영역은 시작 칸에만 rowSpan/colSpan을 채우고, 병합에 덮인 나머지 칸은
 * 아예 결과 행에서 제외한다(HTML table rowSpan/colSpan 규칙과 동일).
 */
export function buildSheetGrid(XLSX, worksheet) {
  const ref = worksheet['!ref']
  if (!ref) {
    return { rows: [], rowCount: 0, colCount: 0, truncatedRows: false, truncatedCols: false }
  }

  const range = XLSX.utils.decode_range(ref)
  const totalRowCount = range.e.r - range.s.r + 1
  const totalColCount = range.e.c - range.s.c + 1
  const rowCount = Math.min(totalRowCount, MAX_RENDER_ROWS)
  const colCount = Math.min(totalColCount, MAX_RENDER_COLS)

  const merges = worksheet['!merges'] || []
  const mergeAnchor = new Map() // "r:c" → { rowSpan, colSpan }
  const mergeSkip = new Set()   // "r:c" → 병합에 덮여 렌더링에서 제외되는 칸

  for (const m of merges) {
    const rowSpan = m.e.r - m.s.r + 1
    const colSpan = m.e.c - m.s.c + 1
    mergeAnchor.set(`${m.s.r}:${m.s.c}`, { rowSpan, colSpan })
    for (let r = m.s.r; r <= m.e.r; r++) {
      for (let c = m.s.c; c <= m.e.c; c++) {
        if (r === m.s.r && c === m.s.c) continue
        mergeSkip.add(`${r}:${c}`)
      }
    }
  }

  const rows = []
  for (let r = range.s.r; r < range.s.r + rowCount; r++) {
    const cells = []
    for (let c = range.s.c; c < range.s.c + colCount; c++) {
      const key = `${r}:${c}`
      if (mergeSkip.has(key)) continue
      const addr = XLSX.utils.encode_cell({ r, c })
      const span = mergeAnchor.get(key)
      cells.push({
        row: r,
        col: c,
        value: XLSX.utils.format_cell(worksheet[addr]),
        rowSpan: span ? span.rowSpan : 1,
        colSpan: span ? span.colSpan : 1,
      })
    }
    rows.push(cells)
  }

  return {
    rows,
    rowCount,
    colCount,
    truncatedRows: totalRowCount > MAX_RENDER_ROWS,
    truncatedCols: totalColCount > MAX_RENDER_COLS,
  }
}
