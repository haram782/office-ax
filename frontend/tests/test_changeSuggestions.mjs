/**
 * changeSuggestions.js 단위 테스트 — Node.js 내장 assert 사용, 외부 의존 없음.
 *
 * 실행: node frontend/tests/test_changeSuggestions.mjs
 */
import assert from 'node:assert/strict'
import { deriveChangeSuggestions } from '../src/utils/changeSuggestions.js'

let passed = 0
let failed = 0

function test(name, fn) {
  try {
    fn()
    console.log(`  ✓ ${name}`)
    passed++
  } catch (err) {
    console.error(`  ✗ ${name}`)
    console.error(`    ${err.message}`)
    failed++
  }
}

// ── null / 빈 입력 ─────────────────────────────────────────────────────────────

console.log('\n[null / 빈 입력]')

test('null snippetData는 빈 배열을 반환한다', () => {
  assert.deepEqual(deriveChangeSuggestions(null), [])
})

test('undefined snippetData는 빈 배열을 반환한다', () => {
  assert.deepEqual(deriveChangeSuggestions(undefined), [])
})

test('빈 객체 snippetData는 빈 배열을 반환한다', () => {
  assert.deepEqual(deriveChangeSuggestions({}), [])
})

test('세 소스 모두 빈 배열이면 빈 배열을 반환한다', () => {
  const snippetData = { corrections: [], change_highlights: [], edit_suggestions: [] }
  assert.deepEqual(deriveChangeSuggestions(snippetData), [])
})

// ── corrections 변환 ──────────────────────────────────────────────────────────

console.log('\n[corrections 변환]')

test('corrections만 있는 Excel snippetData를 변환한다', () => {
  const snippetData = {
    type: 'excel_preview',
    corrections: [
      { cell: 'D12', original: '-15,000', corrected: '15,000', severity: 'error' },
      { cell: 'B34', original: '#REF!',   corrected: '=SUM(E2:E33)' },
    ],
  }
  const result = deriveChangeSuggestions(snippetData)
  assert.equal(result.length, 2)
})

test('correction의 source는 "corrections"다', () => {
  const snippetData = { corrections: [{ cell: 'A1', original: 'x', corrected: 'y' }] }
  const [s] = deriveChangeSuggestions(snippetData)
  assert.equal(s.source, 'corrections')
})

test('correction의 changeType은 "correction"이다', () => {
  const snippetData = { corrections: [{ cell: 'A1', original: 'x', corrected: 'y' }] }
  const [s] = deriveChangeSuggestions(snippetData)
  assert.equal(s.changeType, 'correction')
})

test('corrected 값이 replacement로 변환된다', () => {
  const snippetData = { corrections: [{ cell: 'D12', original: '-15,000', corrected: '15,000' }] }
  const [s] = deriveChangeSuggestions(snippetData)
  assert.equal(s.replacement, '15,000')
})

test('corrections에 severity 없으면 "info"로 폴백한다', () => {
  const snippetData = { corrections: [{ cell: 'A1', original: 'x', corrected: 'y' }] }
  const [s] = deriveChangeSuggestions(snippetData)
  assert.equal(s.severity, 'info')
})

test('corrections에 status 없으면 "pending"으로 폴백한다', () => {
  const snippetData = { corrections: [{ cell: 'A1', original: 'x', corrected: 'y' }] }
  const [s] = deriveChangeSuggestions(snippetData)
  assert.equal(s.status, 'pending')
})

// ── cell anchor ───────────────────────────────────────────────────────────────

console.log('\n[cell anchor]')

test('cell과 sheet가 있으면 anchor.type이 "cell"이다', () => {
  const snippetData = { corrections: [{ cell: 'D12', sheet: 'Sheet1', original: 'x', corrected: 'y' }] }
  const [s] = deriveChangeSuggestions(snippetData)
  assert.equal(s.anchor.type, 'cell')
  assert.equal(s.anchor.cell, 'D12')
  assert.equal(s.anchor.sheet, 'Sheet1')
})

test('sheet 없는 correction도 cell anchor로 생성된다', () => {
  const snippetData = { corrections: [{ cell: 'B5', original: 'x', corrected: 'y' }] }
  const [s] = deriveChangeSuggestions(snippetData)
  assert.equal(s.anchor.type, 'cell')
  assert.equal(s.anchor.cell, 'B5')
  assert.equal(s.anchor.sheet, '')
})

test('change_highlights target=cell도 cell anchor를 생성한다', () => {
  const snippetData = {
    change_highlights: [{
      id: 'h-1', kind: 'correction', target: 'cell',
      format: 'xlsx', cell: 'C3', sheet: 'Sheet2',
      original: 'old', corrected: 'new',
    }],
  }
  const [s] = deriveChangeSuggestions(snippetData)
  assert.equal(s.anchor.type, 'cell')
  assert.equal(s.anchor.cell, 'C3')
  assert.equal(s.anchor.sheet, 'Sheet2')
})

// ── text_match anchor ─────────────────────────────────────────────────────────

console.log('\n[text_match anchor]')

test('change_highlights target=text이면 anchor.type이 "text_match"다', () => {
  const snippetData = {
    change_highlights: [{
      id: 'h-2', kind: 'masking', target: 'text',
      format: 'docx',
      target_text:    '홍길동',
      context_before: '고객명:',
      context_after:  '님의 주문',
      original: '홍길동', corrected: '***',
    }],
  }
  const [s] = deriveChangeSuggestions(snippetData)
  assert.equal(s.anchor.type, 'text_match')
  assert.equal(s.anchor.target_text, '홍길동')
  assert.equal(s.anchor.context_before, '고객명:')
  assert.equal(s.anchor.context_after, '님의 주문')
})

// ── change_highlights 변환 ────────────────────────────────────────────────────

console.log('\n[change_highlights 변환]')

test('change_highlights만 있는 snippetData를 변환한다', () => {
  const snippetData = {
    type: 'pptx_preview',
    change_highlights: [
      {
        id: 'patch-1-0-0-0', kind: 'patch', target: 'shape',
        format: 'pptx', slide_index: 0, shape_index: 2,
        original: '구버전 텍스트', corrected: '신버전 텍스트',
        source: 'manual_patch',
      },
    ],
  }
  const result = deriveChangeSuggestions(snippetData)
  assert.equal(result.length, 1)
  assert.equal(result[0].source, 'change_highlights')
  assert.equal(result[0].changeType, 'patch')
  assert.equal(result[0].format, 'pptx')
})

test('change_highlights의 corrected가 replacement로 변환된다', () => {
  const snippetData = {
    change_highlights: [{
      id: 'h-1', kind: 'correction', target: 'cell',
      format: 'xlsx', cell: 'A1', original: 'old', corrected: 'new',
    }],
  }
  const [s] = deriveChangeSuggestions(snippetData)
  assert.equal(s.replacement, 'new')
})

test('change_highlights id가 없으면 fallback id가 생성된다', () => {
  const snippetData = {
    change_highlights: [{ kind: 'correction', target: 'cell', cell: 'A1', original: 'x', corrected: 'y' }],
  }
  const [s] = deriveChangeSuggestions(snippetData)
  assert.ok(s.id, 'id가 생성되어야 한다')
  assert.equal(s.id, 'highlight-0')
})

test('correction id가 없으면 fallback id가 생성된다', () => {
  const snippetData = { corrections: [{ cell: 'A1', original: 'x', corrected: 'y' }] }
  const [s] = deriveChangeSuggestions(snippetData)
  assert.equal(s.id, 'correction-0')
})

// ── edit_suggestions 변환 ─────────────────────────────────────────────────────

console.log('\n[edit_suggestions 변환]')

test('edit_suggestions가 있으면 우선 사용된다', () => {
  const snippetData = {
    corrections: [{ cell: 'A1', original: 'old', corrected: 'corrected_val' }],
    edit_suggestions: [{
      id: 'es-1',
      title: '우선 수정',
      original: 'old',
      replacement: 'edit_val',
      anchor: { type: 'cell', cell: 'A1', sheet: '' },
    }],
  }
  const result = deriveChangeSuggestions(snippetData)
  // edit_suggestions가 먼저 나와야 한다
  assert.equal(result[0].source, 'edit_suggestions')
  assert.equal(result[0].replacement, 'edit_val')
})

test('edit_suggestions의 source는 "edit_suggestions"다', () => {
  const snippetData = {
    edit_suggestions: [{
      id: 'es-1', title: '테스트', original: 'a', replacement: 'b',
      anchor: { type: 'cell', cell: 'A1', sheet: '' },
    }],
  }
  const [s] = deriveChangeSuggestions(snippetData)
  assert.equal(s.source, 'edit_suggestions')
})

test('edit_suggestions의 title이 올바르게 매핑된다', () => {
  const snippetData = {
    edit_suggestions: [{
      id: 'es-1', title: '오탈자 수정', original: 'a', replacement: 'b',
      anchor: { type: 'cell', cell: 'A1', sheet: '' },
    }],
  }
  const [s] = deriveChangeSuggestions(snippetData)
  assert.equal(s.title, '오탈자 수정')
})

test('edit_suggestions의 reason이 올바르게 매핑된다', () => {
  const snippetData = {
    edit_suggestions: [{
      id: 'es-1', reason: '맞춤법 오류', original: 'a', replacement: 'b',
      anchor: { type: 'unknown' },
    }],
  }
  const [s] = deriveChangeSuggestions(snippetData)
  assert.equal(s.reason, '맞춤법 오류')
})

// ── 우선순위 및 중복 제거 ─────────────────────────────────────────────────────

console.log('\n[우선순위 및 중복 제거]')

test('edit_suggestions가 동일 anchor를 가지면 change_highlights는 제거된다', () => {
  const snippetData = {
    edit_suggestions: [{
      id: 'es-1', title: '수정', original: 'old', replacement: 'new_es',
      anchor: { type: 'cell', cell: 'B2', sheet: '' },
    }],
    change_highlights: [{
      id: 'h-1', kind: 'correction', target: 'cell',
      format: 'xlsx', cell: 'B2', sheet: '',
      original: 'old', corrected: 'new_h',
    }],
  }
  const result = deriveChangeSuggestions(snippetData)
  // B2 셀에 대해 edit_suggestions만 유지
  assert.equal(result.length, 1)
  assert.equal(result[0].source, 'edit_suggestions')
})

test('edit_suggestions가 동일 anchor를 가지면 corrections도 제거된다', () => {
  const snippetData = {
    edit_suggestions: [{
      id: 'es-1', original: 'old', replacement: 'new_es',
      anchor: { type: 'cell', cell: 'C5', sheet: '' },
    }],
    corrections: [{ cell: 'C5', original: 'old', corrected: 'new_c' }],
  }
  const result = deriveChangeSuggestions(snippetData)
  assert.equal(result.length, 1)
  assert.equal(result[0].source, 'edit_suggestions')
})

test('change_highlights가 동일 anchor를 가지면 corrections는 제거된다', () => {
  const snippetData = {
    change_highlights: [{
      id: 'h-1', kind: 'correction', target: 'cell',
      format: 'xlsx', cell: 'D12', sheet: '',
      original: '-15,000', corrected: '15,000',
    }],
    corrections: [{ cell: 'D12', original: '-15,000', corrected: '15,000' }],
  }
  const result = deriveChangeSuggestions(snippetData)
  assert.equal(result.length, 1)
  assert.equal(result[0].source, 'change_highlights')
})

test('다른 anchor면 모두 포함된다', () => {
  const snippetData = {
    change_highlights: [{
      id: 'h-1', kind: 'correction', target: 'cell',
      format: 'xlsx', cell: 'A1', original: 'x', corrected: 'y',
    }],
    corrections: [{ cell: 'B2', original: 'p', corrected: 'q' }],
  }
  const result = deriveChangeSuggestions(snippetData)
  assert.equal(result.length, 2)
})

// ── patch_changes 최우선순위 ───────────────────────────────────────────────────
// patch_changes만 서버 DocumentChange PK(changeDbId)를 가지므로,
// 동일 anchor를 다른 소스가 가리키더라도 patch_changes가 우선 유지되어야 한다.

console.log('\n[patch_changes 최우선순위]')

test('corrections와 동일 anchor면 patch_changes가 우선 유지된다', () => {
  const snippetData = {
    corrections: [{ cell: 'D12', sheet: 'Sheet1', original: 'old', corrected: 'new_c' }],
    patch_changes: [{
      id: 99, operation_id: 'op-1', original: 'old', replacement: 'new_p',
      anchor: { type: 'cell', cell: 'D12', sheet: 'Sheet1' },
    }],
  }
  const result = deriveChangeSuggestions(snippetData)
  assert.equal(result.length, 1)
  assert.equal(result[0].source, 'patch_changes')
  assert.equal(result[0].changeDbId, 99)
})

test('edit_suggestions와 동일 anchor면 patch_changes가 우선 유지된다', () => {
  const snippetData = {
    edit_suggestions: [{
      id: 'es-1', original: 'old', replacement: 'new_es',
      anchor: { type: 'cell', cell: 'B2', sheet: '' },
    }],
    patch_changes: [{
      id: 101, operation_id: 'op-2', original: 'old', replacement: 'new_p',
      anchor: { type: 'cell', cell: 'B2', sheet: '' },
    }],
  }
  const result = deriveChangeSuggestions(snippetData)
  assert.equal(result.length, 1)
  assert.equal(result[0].source, 'patch_changes')
  assert.equal(result[0].changeDbId, 101)
})

test('change_highlights와 동일 anchor면 patch_changes가 우선 유지된다', () => {
  const snippetData = {
    change_highlights: [{
      id: 'h-1', kind: 'correction', target: 'cell',
      format: 'xlsx', cell: 'C3', sheet: 'Sheet2', original: 'old', corrected: 'new_h',
    }],
    patch_changes: [{
      id: 102, operation_id: 'op-3', original: 'old', replacement: 'new_p',
      anchor: { type: 'cell', cell: 'C3', sheet: 'Sheet2' },
    }],
  }
  const result = deriveChangeSuggestions(snippetData)
  assert.equal(result.length, 1)
  assert.equal(result[0].source, 'patch_changes')
  assert.equal(result[0].changeDbId, 102)
})

test('patch_changes가 없으면 기존 우선순위(edit_suggestions > change_highlights > corrections)가 유지된다', () => {
  const snippetData = {
    edit_suggestions: [{
      id: 'es-1', original: 'old', replacement: 'new_es',
      anchor: { type: 'cell', cell: 'F1', sheet: '' },
    }],
    change_highlights: [{
      id: 'h-1', kind: 'correction', target: 'cell',
      format: 'xlsx', cell: 'F1', sheet: '', original: 'old', corrected: 'new_h',
    }],
    corrections: [{ cell: 'F1', original: 'old', corrected: 'new_c' }],
  }
  const result = deriveChangeSuggestions(snippetData)
  assert.equal(result.length, 1)
  assert.equal(result[0].source, 'edit_suggestions')
})

test('서로 다른 anchor를 가진 4개 소스는 모두 결과에 포함된다 (병합이 아닌 순서 변경)', () => {
  const snippetData = {
    patch_changes: [{
      id: 200, operation_id: 'op-4', original: 'a', replacement: 'a2',
      anchor: { type: 'cell', cell: 'A1', sheet: '' },
    }],
    edit_suggestions: [{
      id: 'es-1', original: 'b', replacement: 'b2',
      anchor: { type: 'cell', cell: 'B1', sheet: '' },
    }],
    change_highlights: [{
      id: 'h-1', kind: 'correction', target: 'cell',
      format: 'xlsx', cell: 'C1', sheet: '', original: 'c', corrected: 'c2',
    }],
    corrections: [{ cell: 'D1', original: 'd', corrected: 'd2' }],
  }
  const result = deriveChangeSuggestions(snippetData)
  assert.equal(result.length, 4)
  const sources = result.map(s => s.source).sort()
  assert.deepEqual(sources, ['change_highlights', 'corrections', 'edit_suggestions', 'patch_changes'])
})

test('patch_changes 항목의 anchor가 null이면 중복 제거 대상에서 제외되어 그대로 포함된다', () => {
  const snippetData = {
    corrections: [{ cell: 'A1', original: 'x', corrected: 'y' }],
    patch_changes: [
      { id: 300, operation_id: 'op-5', original: 'm', replacement: 'm2', anchor: null },
      { id: 301, operation_id: 'op-6', original: 'n', replacement: 'n2', anchor: null },
    ],
  }
  const result = deriveChangeSuggestions(snippetData)
  // anchor가 null(→ anchorKey도 null)인 두 patch_changes 항목은 중복 판정 없이 모두 포함되고,
  // 별도 anchor를 가진 corrections 항목도 그대로 포함되어 총 3건이어야 한다
  assert.equal(result.length, 3)
  const patchResults = result.filter(s => s.source === 'patch_changes')
  assert.equal(patchResults.length, 2)
  assert.equal(patchResults[0].changeDbId, 300)
  assert.equal(patchResults[1].changeDbId, 301)
})

test('changeDbId는 patch_changes만 채워지고 다른 소스는 null이다', () => {
  const snippetData = {
    edit_suggestions: [{ id: 'es-1', original: 'a', replacement: 'b', anchor: { type: 'cell', cell: 'X1', sheet: '' } }],
    change_highlights: [{ id: 'h-1', kind: 'correction', target: 'cell', format: 'xlsx', cell: 'X2', sheet: '', original: 'a', corrected: 'b' }],
    corrections: [{ cell: 'X3', original: 'a', corrected: 'b' }],
    patch_changes: [{ id: 999, operation_id: 'op-7', original: 'a', replacement: 'b', anchor: { type: 'cell', cell: 'X4', sheet: '' } }],
  }
  const result = deriveChangeSuggestions(snippetData)
  const byTarget = Object.fromEntries(result.map(s => [s.source, s.changeDbId]))
  assert.equal(byTarget.edit_suggestions, null)
  assert.equal(byTarget.change_highlights, null)
  assert.equal(byTarget.corrections, null)
  assert.equal(byTarget.patch_changes, 999)
})

// ── format 유추 ────────────────────────────────────────────────────────────────

console.log('\n[format 유추]')

test('snippetData.type=excel_preview이면 format이 "xlsx"로 유추된다', () => {
  const snippetData = {
    type: 'excel_preview',
    corrections: [{ cell: 'A1', original: 'x', corrected: 'y' }],
  }
  const [s] = deriveChangeSuggestions(snippetData)
  assert.equal(s.format, 'xlsx')
})

test('opts.format이 주어지면 snippetData.type보다 우선 적용된다', () => {
  const snippetData = {
    type: 'excel_preview',
    corrections: [{ cell: 'A1', original: 'x', corrected: 'y' }],
  }
  const [s] = deriveChangeSuggestions(snippetData, { format: 'csv' })
  assert.equal(s.format, 'csv')
})

test('type을 알 수 없으면 format이 "unknown"이 된다', () => {
  const snippetData = { corrections: [{ cell: 'A1', original: 'x', corrected: 'y' }] }
  const [s] = deriveChangeSuggestions(snippetData)
  assert.equal(s.format, 'unknown')
})

test('change_highlights에 format이 이미 있으면 그대로 유지된다', () => {
  const snippetData = {
    change_highlights: [{
      id: 'h-1', kind: 'correction', target: 'cell',
      format: 'pptx', cell: 'A1', original: 'x', corrected: 'y',
    }],
  }
  const [s] = deriveChangeSuggestions(snippetData)
  assert.equal(s.format, 'pptx')
})

// ── 불변성 ─────────────────────────────────────────────────────────────────────

console.log('\n[불변성]')

test('원본 snippetData 객체를 mutate하지 않는다', () => {
  const original = { cell: 'A1', original: 'x', corrected: 'y' }
  const snippetData = { corrections: [original] }
  const before = JSON.stringify(snippetData)

  deriveChangeSuggestions(snippetData)

  assert.equal(JSON.stringify(snippetData), before, '원본 객체가 변경되지 않아야 한다')
})

test('반환된 suggestion을 수정해도 원본 snippetData에 영향을 주지 않는다', () => {
  const c = { cell: 'A1', original: 'x', corrected: 'y' }
  const snippetData = { corrections: [c] }

  const result = deriveChangeSuggestions(snippetData)
  // 반환된 suggestion 수정 시도
  result[0].replacement = 'MUTATED'
  result[0].anchor.cell = 'MUTATED'

  // 원본은 변경되지 않아야 한다
  assert.equal(c.corrected, 'y')
  assert.equal(c.cell, 'A1')
})

// ── set_cell_style patch_changes 변환 (v1 XLSX style POC) ───────────────────────

console.log('\n[set_cell_style patch_changes 변환]')

test('set_cell_style의 operation 필드가 보존된다', () => {
  const snippetData = {
    patch_changes: [{
      id: 500, operation_id: 'op_style_1', format: 'xlsx', operation: 'set_cell_style',
      title: '표 헤더 서식 정리', original: '', replacement: '',
      anchor: { type: 'cell_range', sheet: 'Sheet1', range: 'A1:D1' },
      patch: { font_bold: true, fill_color: 'D9EAF7' },
    }],
  }
  const [s] = deriveChangeSuggestions(snippetData)
  assert.equal(s.operation, 'set_cell_style')
})

test('set_cell_style의 patch 객체가 보존된다', () => {
  const snippetData = {
    patch_changes: [{
      id: 501, operation_id: 'op_style_2', format: 'xlsx', operation: 'set_cell_style',
      anchor: { type: 'cell_range', sheet: 'Sheet1', range: 'A1:D1' },
      patch: { font_bold: true, fill_color: 'D9EAF7', horizontal_alignment: 'center', border: 'thin' },
    }],
  }
  const [s] = deriveChangeSuggestions(snippetData)
  assert.deepEqual(s.patch, { font_bold: true, fill_color: 'D9EAF7', horizontal_alignment: 'center', border: 'thin' })
})

test('patch가 없는 patch_changes 항목은 빈 객체로 폴백한다', () => {
  const snippetData = {
    patch_changes: [{ id: 502, operation_id: 'op_replace', original: 'a', replacement: 'b', anchor: { type: 'cell', cell: 'A1', sheet: '' } }],
  }
  const [s] = deriveChangeSuggestions(snippetData)
  assert.deepEqual(s.patch, {})
})

test('operation이 없는 patch_changes 항목(예: replace_cell 레거시 응답)은 빈 문자열로 폴백한다', () => {
  const snippetData = {
    patch_changes: [{ id: 503, operation_id: 'op_legacy', original: 'a', replacement: 'b', anchor: { type: 'cell', cell: 'A1', sheet: '' } }],
  }
  const [s] = deriveChangeSuggestions(snippetData)
  assert.equal(s.operation, '')
})

test('cell_range anchor가 그대로 보존된다', () => {
  const snippetData = {
    patch_changes: [{
      id: 504, operation_id: 'op_style_3', operation: 'set_cell_style',
      anchor: { type: 'cell_range', sheet: 'Sheet1', range: 'A1:D1' },
      patch: { font_bold: true },
    }],
  }
  const [s] = deriveChangeSuggestions(snippetData)
  assert.equal(s.anchor.type, 'cell_range')
  assert.equal(s.anchor.sheet, 'Sheet1')
  assert.equal(s.anchor.range, 'A1:D1')
})

test('동일 시트+range의 set_cell_style 두 건은 중복 제거된다(우선 항목만 유지)', () => {
  const snippetData = {
    patch_changes: [
      { id: 600, operation_id: 'op_a', operation: 'set_cell_style', anchor: { type: 'cell_range', sheet: 'Sheet1', range: 'A1:D1' }, patch: { font_bold: true } },
    ],
    edit_suggestions: [
      { id: 'es-dup', anchor: { type: 'cell_range', sheet: 'Sheet1', range: 'A1:D1' }, original: '', replacement: '' },
    ],
  }
  const result = deriveChangeSuggestions(snippetData)
  assert.equal(result.length, 1)
  assert.equal(result[0].source, 'patch_changes')
})

test('다른 range를 가진 cell_range는 모두 포함된다', () => {
  const snippetData = {
    patch_changes: [
      { id: 601, operation_id: 'op_b1', operation: 'set_cell_style', anchor: { type: 'cell_range', sheet: 'Sheet1', range: 'A1:D1' }, patch: {} },
      { id: 602, operation_id: 'op_b2', operation: 'set_cell_style', anchor: { type: 'cell_range', sheet: 'Sheet1', range: 'A2:D2' }, patch: {} },
    ],
  }
  const result = deriveChangeSuggestions(snippetData)
  assert.equal(result.length, 2)
})

// ── 결과 출력 ──────────────────────────────────────────────────────────────────

console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`)
if (failed > 0) process.exit(1)
