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

// ── 결과 출력 ──────────────────────────────────────────────────────────────────

console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`)
if (failed > 0) process.exit(1)
