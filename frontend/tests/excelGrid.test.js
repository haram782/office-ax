import { describe, it, expect } from 'vitest'
import * as XLSX from 'xlsx'
import { buildSheetGrid } from '../src/utils/excelGrid'

describe('buildSheetGrid', () => {
  it('!ref가 없는 빈 시트는 빈 grid를 반환한다', () => {
    const grid = buildSheetGrid(XLSX, {})

    expect(grid.rows).toEqual([])
    expect(grid.rowCount).toBe(0)
    expect(grid.colCount).toBe(0)
    expect(grid.colWidths).toEqual([])
    expect(grid.rowHeights).toEqual([])
  })

  it('병합 없는 단순 표는 각 셀이 rowSpan/colSpan 1로 그대로 렌더된다', () => {
    const ws = {
      '!ref': 'A1:B2',
      A1: { t: 's', v: '이름' },
      B1: { t: 's', v: '나이' },
      A2: { t: 's', v: '홍길동' },
      B2: { t: 'n', v: 30 },
    }

    const grid = buildSheetGrid(XLSX, ws)

    expect(grid.rowCount).toBe(2)
    expect(grid.colCount).toBe(2)
    expect(grid.rows).toEqual([
      [
        { row: 0, col: 0, value: '이름', align: 'left', rowSpan: 1, colSpan: 1 },
        { row: 0, col: 1, value: '나이', align: 'left', rowSpan: 1, colSpan: 1 },
      ],
      [
        { row: 1, col: 0, value: '홍길동', align: 'left', rowSpan: 1, colSpan: 1 },
        { row: 1, col: 1, value: '30', align: 'right', rowSpan: 1, colSpan: 1 },
      ],
    ])
  })

  it('숫자 셀은 오른쪽 정렬, 문자열 셀은 왼쪽 정렬 — 엑셀 기본 정렬과 동일하게 맞춘다', () => {
    const ws = { '!ref': 'A1:B1', A1: { t: 'n', v: 5 }, B1: { t: 's', v: '텍스트' } }

    const grid = buildSheetGrid(XLSX, ws)

    expect(grid.rows[0][0].align).toBe('right')
    expect(grid.rows[0][1].align).toBe('left')
  })

  it('비어 있는 셀은 빈 문자열 값·왼쪽 정렬로 렌더된다', () => {
    const ws = { '!ref': 'A1:B1', A1: { t: 's', v: '이름' } }

    const grid = buildSheetGrid(XLSX, ws)

    expect(grid.rows[0][1]).toEqual({ row: 0, col: 1, value: '', align: 'left', rowSpan: 1, colSpan: 1 })
  })

  it('[핵심] 병합 셀은 시작 칸에 rowSpan/colSpan을 채우고, 덮인 칸은 아예 렌더 목록에서 제외한다', () => {
    // 폼 스타일 문서에서 흔한 "라벨 1칸 + 값 3칸 병합" 구조
    const ws = {
      '!ref': 'A1:D1',
      A1: { t: 's', v: '주소' },
      B1: { t: 's', v: '분당동 102-1' },
      '!merges': [{ s: { r: 0, c: 1 }, e: { r: 0, c: 3 } }],
    }

    const grid = buildSheetGrid(XLSX, ws)

    expect(grid.rows[0]).toEqual([
      { row: 0, col: 0, value: '주소', align: 'left', rowSpan: 1, colSpan: 1 },
      { row: 0, col: 1, value: '분당동 102-1', align: 'left', rowSpan: 1, colSpan: 3 },
    ])
  })

  it('세로 병합도 동일하게 처리한다', () => {
    const ws = {
      '!ref': 'A1:A2',
      A1: { t: 's', v: '결재' },
      '!merges': [{ s: { r: 0, c: 0 }, e: { r: 1, c: 0 } }],
    }

    const grid = buildSheetGrid(XLSX, ws)

    expect(grid.rows).toEqual([
      [{ row: 0, col: 0, value: '결재', align: 'left', rowSpan: 2, colSpan: 1 }],
      [],
    ])
  })

  it('시트가 A1이 아닌 위치에서 시작해도 row/col은 실제(절대) 좌표를 유지한다 — anchor.cell(openpyxl A1 표기)과 정렬되어야 함', () => {
    const ws = { '!ref': 'B2:C2', B2: { t: 's', v: 'X' }, C2: { t: 's', v: 'Y' } }

    const grid = buildSheetGrid(XLSX, ws)

    expect(grid.startRow).toBe(1)
    expect(grid.startCol).toBe(1)
    expect(grid.rows[0]).toEqual([
      { row: 1, col: 1, value: 'X', align: 'left', rowSpan: 1, colSpan: 1 },
      { row: 1, col: 2, value: 'Y', align: 'left', rowSpan: 1, colSpan: 1 },
    ])
  })

  it('숫자 포맷 셀은 서식이 반영된 표시 문자열(.w)로 렌더된다', () => {
    const ws = {
      '!ref': 'A1:A1',
      A1: { t: 'n', v: 45153, z: 'yyyy"년" mm"월" dd"일"', w: '2023년 8월 15일' },
    }

    const grid = buildSheetGrid(XLSX, ws)

    expect(grid.rows[0][0].value).toBe('2023년 8월 15일')
  })

  describe('열 너비 · 행 높이 — 실제 엑셀과 같은 비율로 보이려면 필수', () => {
    it('워크시트에 !cols/!rows 픽셀값이 있으면 그대로 반영한다', () => {
      const ws = {
        '!ref': 'A1:B2',
        '!cols': [{ wpx: 77 }, { wpx: 120 }],
        '!rows': [{ hpx: 19.5 }, { hpx: 30 }],
      }

      const grid = buildSheetGrid(XLSX, ws)

      expect(grid.colWidths).toEqual([77, 120])
      expect(grid.rowHeights).toEqual([20, 30]) // 19.5 → 반올림
    })

    it('!cols/!rows가 없으면 엑셀 기본값에 준하는 값으로 대체한다', () => {
      const ws = { '!ref': 'A1:B2' }

      const grid = buildSheetGrid(XLSX, ws)

      expect(grid.colWidths).toEqual([64, 64])
      expect(grid.rowHeights).toEqual([20, 20])
    })

    it('!cols 배열이 일부 컬럼만 채워져 있으면 나머지는 기본값을 쓴다', () => {
      const ws = { '!ref': 'A1:C1', '!cols': [{ wpx: 100 }] }

      const grid = buildSheetGrid(XLSX, ws)

      expect(grid.colWidths).toEqual([100, 64, 64])
    })

    it('시트가 A1이 아닌 위치에서 시작하면 !cols/!rows도 절대 인덱스로 조회한다', () => {
      // !cols[1]/!rows[1] = 컬럼 B/행 2 (0-based index 1) — 시작 위치와 무관하게 절대 인덱스
      const ws = {
        '!ref': 'B2:B2',
        '!cols': [{ wpx: 10 }, { wpx: 99 }],
        '!rows': [{ hpx: 10 }, { hpx: 88 }],
      }

      const grid = buildSheetGrid(XLSX, ws)

      expect(grid.colWidths).toEqual([99])
      expect(grid.rowHeights).toEqual([88])
    })
  })

  it('시트 크기가 상한을 넘으면 잘라내고 truncated 플래그를 켠다', () => {
    const ws = { '!ref': 'A1:BZ1' } // 78개 컬럼 > MAX_RENDER_COLS(60)

    const grid = buildSheetGrid(XLSX, ws)

    expect(grid.colCount).toBe(60)
    expect(grid.truncatedCols).toBe(true)
    expect(grid.colWidths).toHaveLength(60)
  })
})
