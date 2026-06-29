/**
 * useChangeSuggestions.js의 순수 함수 단위 테스트.
 * React 훅 자체는 DOM 환경이 필요하므로 여기서는 buildInitialStatuses만 검증한다.
 *
 * 실행: node frontend/tests/test_useChangeSuggestions.mjs
 */
import assert from 'node:assert/strict'

// React 의존성 없이 순수 함수만 로드 — changeSuggestions.js에서 직접 임포트
import { buildInitialStatuses } from '../src/utils/changeSuggestions.js'

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

// ── 기본 동작 ──────────────────────────────────────────────────────────────────

console.log('\n[buildInitialStatuses 기본 동작]')

test('빈 배열은 빈 맵을 반환한다', () => {
  assert.deepEqual(buildInitialStatuses([]), {})
})

test('pending 상태는 그대로 유지된다', () => {
  const result = buildInitialStatuses([{ id: 'a', status: 'pending' }])
  assert.equal(result['a'], 'pending')
})

test('applied 상태는 그대로 유지된다', () => {
  const result = buildInitialStatuses([{ id: 'b', status: 'applied' }])
  assert.equal(result['b'], 'applied')
})

test('rejected 상태는 그대로 유지된다', () => {
  const result = buildInitialStatuses([{ id: 'c', status: 'rejected' }])
  assert.equal(result['c'], 'rejected')
})

test('status가 없으면 pending으로 폴백한다', () => {
  const result = buildInitialStatuses([{ id: 'd' }])
  assert.equal(result['d'], 'pending')
})

// ── accepted → applied normalize ─────────────────────────────────────────────

console.log('\n[accepted → applied normalize]')

test('accepted는 applied로 변환된다', () => {
  const result = buildInitialStatuses([{ id: 'e', status: 'accepted' }])
  assert.equal(result['e'], 'applied')
})

test('여러 항목 중 accepted만 applied로 변환된다', () => {
  const suggestions = [
    { id: 'x', status: 'accepted' },
    { id: 'y', status: 'pending' },
    { id: 'z', status: 'rejected' },
  ]
  const result = buildInitialStatuses(suggestions)
  assert.equal(result['x'], 'applied')
  assert.equal(result['y'], 'pending')
  assert.equal(result['z'], 'rejected')
})

// ── 불변성 ─────────────────────────────────────────────────────────────────────

console.log('\n[불변성]')

test('원본 suggestions 배열을 mutate하지 않는다', () => {
  const suggestions = [{ id: 'f', status: 'accepted' }]
  const before = JSON.stringify(suggestions)
  buildInitialStatuses(suggestions)
  assert.equal(JSON.stringify(suggestions), before)
})

test('반환된 맵이 독립적인 객체다', () => {
  const suggestions = [{ id: 'g', status: 'pending' }]
  const result = buildInitialStatuses(suggestions)
  result['g'] = 'mutated'
  // 두 번째 호출 결과가 첫 번째 변형에 영향받지 않는다
  const result2 = buildInitialStatuses(suggestions)
  assert.equal(result2['g'], 'pending')
})

// ── 결과 출력 ──────────────────────────────────────────────────────────────────

console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`)
if (failed > 0) process.exit(1)
