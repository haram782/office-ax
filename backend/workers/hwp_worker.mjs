/**
 * HWP 텍스트 치환 Node.js worker.
 *
 * stdin  : JSON { input_b64, changes }
 * stdout : JSON { applied, failed, output_b64 }
 * stderr : 로그 전용
 *
 * 처리 흐름:
 *   1. stdin 전체 읽기 → JSON 파싱
 *   2. input_b64 → Buffer → Uint8Array
 *   3. @rhwp/core initRhwp() WASM 초기화 (파일시스템 경로 직접 사용)
 *   4. new HwpDocument(bytes) 로 HWP 로드
 *   5. changes 순회 → searchAllText로 존재 확인 후 replaceAll 치환
 *   6. exportHwpVerify() 검증 → exportHwp() → base64 인코딩
 *   7. JSON 출력 후 종료
 */

// frontend 설치본 재사용 — 별도 npm install 불필요
import initRhwp, { HwpDocument } from '../../frontend/node_modules/@rhwp/core/rhwp.js';

// ── stdin 읽기 헬퍼 ────────────────────────────────────────────────────────────

/**
 * stdin 전체를 읽어 문자열로 반환한다.
 * @returns {Promise<string>}
 */
async function readStdin() {
  const chunks = [];
  for await (const chunk of process.stdin) {
    chunks.push(chunk);
  }
  return Buffer.concat(chunks).toString('utf-8');
}

// ── 메인 ──────────────────────────────────────────────────────────────────────

async function main() {
  let input;
  try {
    const raw = await readStdin();
    input = JSON.parse(raw);
  } catch (err) {
    process.stderr.write(`[hwp_worker] stdin 파싱 실패: ${err.message}\n`);
    process.exit(1);
  }

  const { input_b64, changes } = input;

  // base64 → Uint8Array
  const hwpBytes = new Uint8Array(Buffer.from(input_b64, 'base64'));

  // WASM 초기화 — rhwp.js 옆의 .wasm 파일 경로를 직접 지정
  const wasmPath = new URL(
    '../../frontend/node_modules/@rhwp/core/rhwp_bg.wasm',
    import.meta.url
  );
  try {
    await initRhwp({ module_or_path: wasmPath });
  } catch (err) {
    process.stderr.write(`[hwp_worker] WASM 초기화 실패: ${err.message}\n`);
    process.exit(1);
  }

  // HWP 문서 로드
  let doc;
  try {
    doc = new HwpDocument(hwpBytes);
  } catch (err) {
    process.stderr.write(`[hwp_worker] HWP 로드 실패: ${err.message}\n`);
    process.exit(1);
  }

  const applied = [];
  const failed = [];

  // changes 순회 — v0: occurrence 무관하게 replaceAll 사용
  for (const change of (changes || [])) {
    const { operation_id, original, replacement } = change;

    // 대상 텍스트 존재 여부 확인
    let searchResult;
    try {
      const resultJson = doc.searchAllText(original, false, true);
      searchResult = JSON.parse(resultJson);
    } catch (err) {
      process.stderr.write(`[hwp_worker] searchAllText 실패 op=${operation_id}: ${err.message}\n`);
      failed.push({ operation_id, reason: `searchAllText 오류: ${err.message}` });
      continue;
    }

    // 검색 결과가 없으면 실패로 마킹
    if (!searchResult || (Array.isArray(searchResult) && searchResult.length === 0)) {
      process.stderr.write(`[hwp_worker] 텍스트 없음 op=${operation_id}: "${original}"\n`);
      failed.push({ operation_id, reason: '텍스트를 찾을 수 없습니다.' });
      continue;
    }

    // replaceAll로 전체 치환 (v0 단순화 — occurrence별 부분 치환 미구현)
    try {
      doc.replaceAll(original, replacement, false);
      applied.push(operation_id);
      process.stderr.write(`[hwp_worker] 치환 성공 op=${operation_id}: "${original}" → "${replacement}"\n`);
    } catch (err) {
      process.stderr.write(`[hwp_worker] replaceAll 실패 op=${operation_id}: ${err.message}\n`);
      failed.push({ operation_id, reason: `replaceAll 오류: ${err.message}` });
    }
  }

  // 적용 항목 없으면 오류 종료
  if (applied.length === 0) {
    process.stderr.write('[hwp_worker] 적용된 변경 항목 없음\n');
    // 오류가 아닌 정상 종료 — Python 쪽에서 applied=[] 를 보고 failed 처리
  }

  // 내보내기 전 검증
  try {
    const verifyJson = doc.exportHwpVerify();
    const verify = JSON.parse(verifyJson);
    if (verify && verify.errors && verify.errors.length > 0) {
      process.stderr.write(`[hwp_worker] exportHwpVerify 경고: ${JSON.stringify(verify.errors)}\n`);
    }
  } catch (err) {
    // 검증 실패는 경고로 기록하고 계속 진행
    process.stderr.write(`[hwp_worker] exportHwpVerify 오류: ${err.message}\n`);
  }

  // HWP 바이너리 내보내기
  let outputBytes;
  try {
    outputBytes = doc.exportHwp();
  } catch (err) {
    process.stderr.write(`[hwp_worker] exportHwp 실패: ${err.message}\n`);
    process.exit(1);
  }

  const output_b64 = Buffer.from(outputBytes).toString('base64');

  // 결과 JSON 출력
  process.stdout.write(JSON.stringify({ applied, failed, output_b64 }));
}

main().catch((err) => {
  process.stderr.write(`[hwp_worker] 예기치 않은 오류: ${err.message}\n${err.stack}\n`);
  process.exit(1);
});
