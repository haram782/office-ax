// 시트당 렌더링 상한 — 비정상적으로 큰 시트가 브라우저 탭을 멈추지 않도록 하는 안전장치.
// 실사용 미리보기 문서 규모(수십~수백 행)를 넉넉히 덮는다.
const MAX_RENDER_ROWS = 500
const MAX_RENDER_COLS = 60

// 엑셀 기본값에 준하는 값 — 시트에 !cols/!rows 지정이 없는 컬럼·행에 사용한다.
// (기본 열 너비 8.43자 ≈ 64px, 기본 행 높이 15pt ≈ 20px)
const DEFAULT_COL_WIDTH_PX = 64
const DEFAULT_ROW_HEIGHT_PX = 20

/**
 * SheetJS worksheet를 병합 셀·열너비·행높이를 반영한 렌더 그리드로 변환한다.
 * "엑셀에서 보는 듯한 뷰"를 만들려면 병합뿐 아니라 실제 열/행 크기 비율도
 * 맞아야 한다 — 콘텐츠 기준 auto-width로는 원본과 비율이 전혀 달라진다.
 *
 * row/col은 워크시트의 실제(절대, 0-based) 좌표를 그대로 유지한다 — 백엔드
 * patcher(backend/apps/documents/patcher.py)가 anchor.cell을 openpyxl A1
 * 표기로 그대로 해석하므로, 프론트 렌더 좌표도 동일한 절대 좌표계를 써야
 * 하이라이트 매칭이 어긋나지 않는다. !cols/!rows도 SheetJS 관례상 절대
 * 인덱스로 조회한다(시트 시작 위치와 무관).
 *
 * 병합 영역은 시작 칸에만 rowSpan/colSpan을 채우고, 병합에 덮인 나머지 칸은
 * 아예 결과 행에서 제외한다(HTML table rowSpan/colSpan 규칙과 동일).
 */
export function buildSheetGrid(XLSX, worksheet) {
  const ref = worksheet['!ref']
  if (!ref) {
    return {
      rows: [], rowCount: 0, colCount: 0, startRow: 0, startCol: 0,
      colWidths: [], rowHeights: [], truncatedRows: false, truncatedCols: false,
    }
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

  const wsCols = worksheet['!cols'] || []
  const wsRows = worksheet['!rows'] || []

  const colWidths = []
  for (let c = range.s.c; c < range.s.c + colCount; c++) {
    const wpx = wsCols[c]?.wpx
    colWidths.push(wpx ? Math.round(wpx) : DEFAULT_COL_WIDTH_PX)
  }
  const rowHeights = []
  for (let r = range.s.r; r < range.s.r + rowCount; r++) {
    const hpx = wsRows[r]?.hpx
    rowHeights.push(hpx ? Math.round(hpx) : DEFAULT_ROW_HEIGHT_PX)
  }

  const rows = []
  for (let r = range.s.r; r < range.s.r + rowCount; r++) {
    const cells = []
    for (let c = range.s.c; c < range.s.c + colCount; c++) {
      const key = `${r}:${c}`
      if (mergeSkip.has(key)) continue
      const addr = XLSX.utils.encode_cell({ r, c })
      const cellObj = worksheet[addr]
      const span = mergeAnchor.get(key)
      cells.push({
        row: r,
        col: c,
        value: XLSX.utils.format_cell(cellObj),
        // 엑셀 기본 정렬 — 숫자는 오른쪽, 문자열/빈칸은 왼쪽
        align: cellObj?.t === 'n' ? 'right' : 'left',
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
    startRow: range.s.r,
    startCol: range.s.c,
    colWidths,
    rowHeights,
    truncatedRows: totalRowCount > MAX_RENDER_ROWS,
    truncatedCols: totalColCount > MAX_RENDER_COLS,
  }
}
