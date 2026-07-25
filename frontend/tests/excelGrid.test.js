import { describe, it, expect } from 'vitest'
import * as XLSX from 'xlsx'
import { buildSheetGrid } from '../src/utils/excelGrid'

describe('buildSheetGrid', () => {
  it('!ref가 없는 빈 시트는 빈 grid를 반환한다', () => {
    const grid = buildSheetGrid(XLSX, {})

    expect(grid.rows).toEqual([])
    expect(grid.rowCount).toBe(0)
    expect(grid.colCount).toBe(0)
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
        { row: 0, col: 0, value: '이름', rowSpan: 1, colSpan: 1 },
        { row: 0, col: 1, value: '나이', rowSpan: 1, colSpan: 1 },
      ],
      [
        { row: 1, col: 0, value: '홍길동', rowSpan: 1, colSpan: 1 },
        { row: 1, col: 1, value: '30', rowSpan: 1, colSpan: 1 },
      ],
    ])
  })

  it('비어 있는 셀은 빈 문자열 값으로 렌더된다', () => {
    const ws = { '!ref': 'A1:B1', A1: { t: 's', v: '이름' } }

    const grid = buildSheetGrid(XLSX, ws)

    expect(grid.rows[0][1]).toEqual({ row: 0, col: 1, value: '', rowSpan: 1, colSpan: 1 })
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
      { row: 0, col: 0, value: '주소', rowSpan: 1, colSpan: 1 },
      { row: 0, col: 1, value: '분당동 102-1', rowSpan: 1, colSpan: 3 },
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
      [{ row: 0, col: 0, value: '결재', rowSpan: 2, colSpan: 1 }],
      [],
    ])
  })

  it('시트가 A1이 아닌 위치에서 시작해도 row/col은 실제(절대) 좌표를 유지한다 — anchor.cell(openpyxl A1 표기)과 정렬되어야 함', () => {
    const ws = { '!ref': 'B2:C2', B2: { t: 's', v: 'X' }, C2: { t: 's', v: 'Y' } }

    const grid = buildSheetGrid(XLSX, ws)

    expect(grid.rows[0]).toEqual([
      { row: 1, col: 1, value: 'X', rowSpan: 1, colSpan: 1 },
      { row: 1, col: 2, value: 'Y', rowSpan: 1, colSpan: 1 },
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
})
