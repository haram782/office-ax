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
 *   5. changes 순회 → searchAllText로 매치 목록 조회 →
 *      change.anchor.occurrence(1-based, 기본값 1)번째 매치를
 *      replaceText(sec, para, charOffset, length, replacement)로 정밀 치환
 *      (replaceAll은 동일 텍스트 전체를 바꿔버려 단일 매치 교체가 불가능하므로 사용하지 않는다)
 *   6. exportHwpVerify() 검증 → exportHwp() → base64 인코딩
 *   7. JSON 출력 후 종료
 */

// frontend 설치본 재사용 — 별도 npm install 불필요
import initRhwp, { HwpDocument } from '../../frontend/node_modules/@rhwp/core/rhwp.js';
import { readFileSync } from 'node:fs';

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

  // WASM 초기화 — Node의 기본 fetch는 file:// URL을 지원하지 않아
  // URL을 그대로 넘기면 내부 fetch()가 실패한다. 바이트를 직접 읽어 전달해 우회한다.
  const wasmPath = new URL(
    '../../frontend/node_modules/@rhwp/core/rhwp_bg.wasm',
    import.meta.url
  );
  try {
    const wasmBytes = readFileSync(wasmPath);
    await initRhwp({ module_or_path: wasmBytes });
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

  // changes 순회 — searchAllText로 매치 목록을 구한 뒤 occurrence번째 매치만
  // replaceText로 정밀 치환한다 (replaceAll 미사용)
  for (const change of (changes || [])) {
    const { operation_id, original, replacement, anchor } = change;
    // anchor.occurrence: 1-based. 없으면 첫 번째 매치(occurrence=1)를 기본값으로 사용해
    // anchor 정보가 없는 기존 change와도 호환되게 한다.
    const occurrence = (anchor && Number.isInteger(anchor.occurrence) && anchor.occurrence > 0)
      ? anchor.occurrence
      : 1;

    // 매치 목록 조회
    let matches;
    try {
      const resultJson = doc.searchAllText(original, false, true);
      matches = JSON.parse(resultJson);
    } catch (err) {
      process.stderr.write(`[hwp_worker] searchAllText 실패 op=${operation_id}: ${err.message}\n`);
      failed.push({ operation_id, reason: `searchAllText 오류: ${err.message}` });
      continue;
    }

    if (!Array.isArray(matches) || matches.length === 0) {
      process.stderr.write(`[hwp_worker] 텍스트 없음 op=${operation_id}: "${original}"\n`);
      failed.push({ operation_id, reason: '텍스트를 찾을 수 없습니다.' });
      continue;
    }

    // occurrence가 매치 수를 초과하면 실패로 마킹
    if (occurrence > matches.length) {
      process.stderr.write(
        `[hwp_worker] occurrence 범위 초과 op=${operation_id}: occurrence=${occurrence}, 매치=${matches.length}건\n`
      );
      failed.push({ operation_id, reason: `occurrence(${occurrence})가 매치 수(${matches.length})를 초과했습니다.` });
      continue;
    }

    // occurrence번째 매치 1건만 정밀 치환
    const m = matches[occurrence - 1];
    try {
      const replaceResultJson = doc.replaceText(m.sec, m.para, m.charOffset, m.length, replacement);
      const replaceResult = JSON.parse(replaceResultJson);
      if (!replaceResult || replaceResult.ok !== true) {
        process.stderr.write(`[hwp_worker] replaceText 실패 op=${operation_id}\n`);
        failed.push({ operation_id, reason: 'replaceText가 실패를 반환했습니다.' });
        continue;
      }
      applied.push(operation_id);
      process.stderr.write(
        `[hwp_worker] 치환 성공 op=${operation_id}: "${original}"(${occurrence}번째) → "${replacement}"\n`
      );
    } catch (err) {
      process.stderr.write(`[hwp_worker] replaceText 오류 op=${operation_id}: ${err.message}\n`);
      failed.push({ operation_id, reason: `replaceText 오류: ${err.message}` });
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
