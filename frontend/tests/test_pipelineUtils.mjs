/**
 * pipelineUtils.js 단위 테스트 — Node.js 내장 assert 사용
 * 실행: node frontend/tests/test_pipelineUtils.mjs
 */
import assert from 'node:assert/strict'
import { buildMeta, formatRelative, chunk } from '../src/utils/pipelineUtils.js'

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

// ── buildMeta ────────────────────────────────────────────────────────────────
console.log('buildMeta()')

test('A 타입 — last_run_at 없음', () => {
  assert.equal(buildMeta('A', {}, null), '대화형 트리거 · 수동 실행')
})
test('B 타입 — email 있음, last_run_at 없음', () => {
  assert.equal(buildMeta('B', { email: 'inbox@office-ax.com' }, null), 'inbox@office-ax.com 수신 시')
})
test('B 타입 — email 없음, last_run_at 없음', () => {
  assert.equal(buildMeta('B', {}, null), '이메일 수신 시')
})
test('C 타입 — cron 있음, last_run_at 없음', () => {
  assert.equal(buildMeta('C', { cron: '0 9 * * 1' }, null), '0 9 * * 1')
})
test('C 타입 — cron 없음, last_run_at 없음', () => {
  assert.equal(buildMeta('C', {}, null), '스케줄')
})
test('방금 — 30분 전', () => {
  const t = new Date(Date.now() - 30 * 60 * 1000).toISOString()
  assert.ok(buildMeta('A', {}, t).endsWith('· 최근 실행 방금'))
})
test('N시간 전 — 5시간 전', () => {
  const t = new Date(Date.now() - 5 * 3600 * 1000).toISOString()
  assert.ok(buildMeta('A', {}, t).endsWith('· 최근 실행 5시간 전'))
})
test('N일 전 — 3일 전', () => {
  const t = new Date(Date.now() - 3 * 86400 * 1000).toISOString()
  assert.ok(buildMeta('A', {}, t).endsWith('· 최근 실행 3일 전'))
})
test('B 타입 — email + 2시간 전', () => {
  const t = new Date(Date.now() - 2 * 3600 * 1000).toISOString()
  assert.equal(buildMeta('B', { email: 'test@example.com' }, t), 'test@example.com 수신 시 · 최근 실행 2시간 전')
})

// ── formatRelative ────────────────────────────────────────────────────────────
console.log('\nformatRelative()')

test('방금 전 — 0초', () => {
  assert.equal(formatRelative(new Date()), '방금 전')
})
test('방금 전 — 30초', () => {
  assert.equal(formatRelative(new Date(Date.now() - 30_000)), '방금 전')
})
test('1분 전 — 75초', () => {
  assert.equal(formatRelative(new Date(Date.now() - 75_000)), '1분 전')
})
test('45분 전', () => {
  assert.equal(formatRelative(new Date(Date.now() - 45 * 60_000)), '45분 전')
})
test('1시간 전 — 60분', () => {
  assert.equal(formatRelative(new Date(Date.now() - 60 * 60_000)), '1시간 전')
})
test('2시간 전', () => {
  assert.equal(formatRelative(new Date(Date.now() - 120 * 60_000)), '2시간 전')
})

// ── chunk ─────────────────────────────────────────────────────────────────────
console.log('\nchunk()')

test('기본 분할 [1..5] size=2', () => {
  assert.deepEqual(chunk([1, 2, 3, 4, 5], 2), [[1, 2], [3, 4], [5]])
})
test('빈 배열', () => {
  assert.deepEqual(chunk([], 3), [])
})
test('딱 맞는 크기', () => {
  assert.deepEqual(chunk([1, 2, 3], 3), [[1, 2, 3]])
})
test('크기 초과', () => {
  assert.deepEqual(chunk([1], 3), [[1]])
})
test('정확히 2배', () => {
  assert.deepEqual(chunk([1, 2, 3, 4], 2), [[1, 2], [3, 4]])
})

console.log(`\n${passed} passed, ${failed} failed`)
if (failed > 0) process.exit(1)
