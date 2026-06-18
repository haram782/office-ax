/**
 * fileItemsUtils.js 단위 테스트 — Node.js 내장 assert 사용, 외부 의존 없음.
 *
 * 실행: node frontend/tests/test_fileItemsUtils.mjs
 */
import assert from 'node:assert/strict'
import { resolveAssistantMsg, deriveFileItems } from '../src/utils/fileItemsUtils.js'

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

// ── resolveAssistantMsg ─────────────────────────────────────────────────────

console.log('\n[resolveAssistantMsg]')

test('upload_log.id 일치하는 assistant 메시지를 반환한다 (id 기반 매칭)', () => {
  const userMsg = { role: 'user', upload_log: { id: 10, original_filename: 'a.xlsx' } }
  const assistantA = { role: 'assistant', upload_log: { id: 10 }, artifact_url: '/a.xlsx', snippet_data: {} }
  const assistantB = { role: 'assistant', upload_log: { id: 99 }, artifact_url: '/b.xlsx', snippet_data: {} }
  const messages = [userMsg, assistantB, assistantA]

  const result = resolveAssistantMsg(messages, userMsg)
  assert.equal(result, assistantA, 'id=10인 assistantA를 찾아야 함')
})

test('upload_log 없는 구형 assistant는 위치 기반 폴백으로 반환된다', () => {
  const userMsg = { role: 'user', upload_log: { id: 20, original_filename: 'b.xlsx' } }
  // 구형 메시지 — upload_log 없음
  const legacyAssistant = { role: 'assistant', artifact_url: '/legacy.xlsx', snippet_data: {} }
  const messages = [userMsg, legacyAssistant]

  const result = resolveAssistantMsg(messages, userMsg)
  assert.equal(result, legacyAssistant, '구형 메시지를 위치 기반으로 반환해야 함')
})

test('upload_log 있는 다른 파일의 assistant를 탈취하지 않는다', () => {
  const userA = { role: 'user', upload_log: { id: 30, original_filename: 'a.xlsx' } }
  const userB = { role: 'user', upload_log: { id: 31, original_filename: 'b.xlsx' } }
  // userB의 결과만 존재 (upload_log.id=31)
  const assistantB = { role: 'assistant', upload_log: { id: 31 }, artifact_url: '/b.xlsx' }
  const messages = [userA, userB, assistantB]

  // userA에 대한 매칭은 null이어야 함 (upload_log.id=30 없음, 위치 폴백도 upload_log 있어서 제외)
  const result = resolveAssistantMsg(messages, userA)
  assert.equal(result, null, 'id가 다른 다른 파일 결과를 탈취하지 않아야 함')
})

test('비어있는 메시지 배열에서 null을 반환한다', () => {
  const userMsg = { role: 'user', upload_log: { id: 40, original_filename: 'x.xlsx' } }
  const result = resolveAssistantMsg([], userMsg)
  assert.equal(result, null)
})

test('[user_file, user_text, assistant_no_upload_log] — user_file은 null을 반환해야 한다', () => {
  // assistant(upload_log null)는 user_text 뒤에 위치 → user_file의 턴이 아님
  const userFile = { role: 'user', upload_log: { id: 50, original_filename: 'c.xlsx' } }
  const userText = { role: 'user', upload_log: null, content: '분석 완료됐나요?' }
  const textAssistant = { role: 'assistant', upload_log: null, content: '네, 완료됐습니다.' }
  const messages = [userFile, userText, textAssistant]

  const result = resolveAssistantMsg(messages, userFile)
  // userText가 중간에 있으므로 폴백 검색이 그 이전에서 멈춰야 함 → null
  assert.equal(result, null, '다음 user 메시지 이후의 assistant를 탈취하지 않아야 함')
})

// ── deriveFileItems ─────────────────────────────────────────────────────────

console.log('\n[deriveFileItems]')

test('완료된 파일의 status가 done이고 artifactUrl이 채워진다', () => {
  const userMsg = { role: 'user', upload_log: { id: 1, original_filename: 'r.xlsx', file_url: '/f/r.xlsx', status: 'done' } }
  const assistantMsg = { role: 'assistant', upload_log: { id: 1 }, artifact_url: '/art/r.xlsx', snippet_data: { type: 'excel_preview' } }
  const messages = [userMsg, assistantMsg]

  const items = deriveFileItems(messages)
  assert.equal(items.length, 1)
  assert.equal(items[0].status, 'done')
  assert.equal(items[0].artifactUrl, '/art/r.xlsx')
  assert.deepEqual(items[0].snippetData, { type: 'excel_preview' })
})

test('순서가 뒤집혀 도착한 out-of-order 메시지에서도 id 기반 매칭이 동작한다', () => {
  const userA = { role: 'user', upload_log: { id: 100, original_filename: 'a.xlsx', file_url: '', status: 'done' } }
  const userB = { role: 'user', upload_log: { id: 101, original_filename: 'b.xlsx', file_url: '', status: 'done' } }
  // B의 결과가 A보다 먼저 도착 (out-of-order)
  const assistantB = { role: 'assistant', upload_log: { id: 101 }, artifact_url: '/b.xlsx', snippet_data: null }
  const assistantA = { role: 'assistant', upload_log: { id: 100 }, artifact_url: '/a.xlsx', snippet_data: null }
  const messages = [userA, userB, assistantB, assistantA]

  const items = deriveFileItems(messages)
  // items는 최신 순 → [b, a]
  const itemA = items.find(i => i.id === 100)
  const itemB = items.find(i => i.id === 101)

  assert.equal(itemA?.artifactUrl, '/a.xlsx', 'A 파일이 A 결과를 가져야 함')
  assert.equal(itemB?.artifactUrl, '/b.xlsx', 'B 파일이 B 결과를 가져야 함')
})

test('upload_log 없는 user 메시지는 fileItems에서 제외된다', () => {
  const textUser = { role: 'user', content: '안녕하세요', upload_log: null }
  const textAssistant = { role: 'assistant', content: '파일을 첨부해주세요.', upload_log: null }
  const messages = [textUser, textAssistant]

  const items = deriveFileItems(messages)
  assert.equal(items.length, 0, '텍스트 전용 메시지는 fileItems에 포함되지 않아야 함')
})

// ── 결과 출력 ───────────────────────────────────────────────────────────────

console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`)
if (failed > 0) process.exit(1)
