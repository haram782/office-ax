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
import { searchAllTextWhitespaceTolerant } from './hwp_search_utils.mjs';
import { findNearestEmptyCellForward, sortMatchesSafeFirst } from './hwp_cell_utils.mjs';

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

// ── 표 셀 헬퍼 ────────────────────────────────────────────────────────────────

/**
 * 값 칸에 문단이 여러 개(빈 줄 패딩) 있어도, 라벨/접미사 셀(대개 문단 1개)과
 * 구조가 같아지도록 값을 넣고 나머지 빈 문단은 정리해 문단 1개로 합친다.
 *
 * 처음에는 셀의 verticalAlign(top/center/bottom)을 읽어 "그에 맞는 문단"에
 * 넣는 방식으로 구현했는데, 그러면 값 칸이 여전히 문단 여러 개로 남아 이웃
 * 셀과 구조가 다르다(문서를 편집기로 열면 여전히 "3줄짜리 칸"으로 보임).
 * 어느 문단에 넣든 나머지를 비우고 합치면 결과가 항상 문단 1개가 되고, 셀
 * 자체의 verticalAlign이 그대로 적용된다 — enum 값이 top/center/bottom 중
 * 무엇을 뜻하는지 추측할 필요가 아예 없어져 더 견고하다.
 */
function insertValueIntoCell(doc, sec, parentPara, ctrlIdx, cellIdx, value) {
  let paraCount = 1;
  try {
    const count = doc.getCellParagraphCount(sec, parentPara, ctrlIdx, cellIdx);
    if (count > 0) paraCount = count;
  } catch { /* 조회 실패 시 문단 1개로 간주 */ }

  const insResult = JSON.parse(doc.insertTextInCell(sec, parentPara, ctrlIdx, cellIdx, 0, 0, value));
  if (insResult?.ok !== true) return false;
  if (paraCount <= 1) return true;

  // 값을 넣은 0번째를 제외한 나머지 빈 문단의 텍스트를 비운다.
  for (let p = 1; p < paraCount; p += 1) {
    try {
      const len = doc.getCellParagraphLength(sec, parentPara, ctrlIdx, cellIdx, p);
      if (len > 0) doc.deleteTextInCell(sec, parentPara, ctrlIdx, cellIdx, p, 0, len);
    } catch { /* 비우기 실패는 무시 — 병합 단계에서 자연히 걸러진다 */ }
  }
  // 1번 문단을 0번에 반복 병합해 문단 1개로 합친다(Backspace at start 방식이라
  // 매번 같은 인덱스 1을 병합 대상으로 쓰면 순서대로 다 합쳐진다).
  for (let i = 1; i < paraCount; i += 1) {
    try {
      const mergeResult = JSON.parse(doc.mergeParagraphInCell(sec, parentPara, ctrlIdx, cellIdx, 1));
      if (mergeResult?.ok !== true) break;
    } catch {
      break; // 병합 실패해도 값 삽입 자체는 이미 성공했으므로 구조 정리만 건너뛴다
    }
  }
  return true;
}

function searchCellMatches(doc, text) {
  try {
    const matches = JSON.parse(doc.searchAllText(text, false, true));
    return Array.isArray(matches) ? matches.filter((m) => m.cellContext) : [];
  } catch {
    return [];
  }
}

/**
 * original이 통째로는 문서에 없지만(예: "대표자 (인)"), 공백으로 나눈 앞부분
 * ("대표자")과 뒷부분("(인)")이 같은 표의 서로 다른 셀에 떨어져 있고 그 사이에
 * 셀 1개가 끼어 있는 경우가 있다 — 라벨/서명란처럼 값 칸이 원래 빈 채로
 * 남아있는 HWP 양식에서 흔한 구조다. original의 모든 분할 지점(head/tail)을
 * 시도해 head 셀 바로 다음 칸 건너 tail과 일치하는 조합을 찾는다. 같은 패턴이
 * 문서에 여러 번(예: 공급자용/공급받는자용 사본) 있을 수 있으므로
 * occurrence(1-based, 문서 등장 순서)로 몇 번째 쌍인지 고른다.
 *
 * 사이 칸의 "비어있음"은 후보 판정에 쓰지 않는다 — 같은 배치 안에서 앞선
 * occurrence가 이미 그 칸을 채우면, occurrence마다 후보 목록이 달라져 뒤
 * occurrence를 못 찾게 된다(예: occurrence=1이 칸을 채우면 occurrence=2 탐색
 * 시 그 칸이 후보에서 빠져 순번이 밀린다). head/tail이 정확히 한 칸을 사이에
 * 두고 있다는 구조적 조건만으로 충분히 신뢰할 수 있는 매칭이다.
 */
function resolveLabelGapValueCell(doc, original, occurrence) {
  const tokens = original.trim().split(/\s+/).filter(Boolean);
  if (tokens.length < 2) return null;

  const candidates = [];
  for (let k = 1; k < tokens.length; k += 1) {
    const head = tokens.slice(0, k).join(' ');
    const tail = tokens.slice(k).join(' ');
    const headMatches = searchCellMatches(doc, head);
    const tailMatches = searchCellMatches(doc, tail);

    for (const h of headMatches) {
      const { sec, cellContext: hc } = h;
      const valueCellIdx = hc.cellIdx + 1;

      const t = tailMatches.find((m) => {
        const tc = m.cellContext;
        return m.sec === sec && tc.parentPara === hc.parentPara && tc.ctrlIdx === hc.ctrlIdx
          && tc.cellIdx === valueCellIdx + 1;
      });
      if (!t) continue;

      candidates.push({ sec, parentPara: hc.parentPara, ctrlIdx: hc.ctrlIdx, valueCellIdx, head, tail });
    }
  }
  if (candidates.length === 0) return null;

  // 문서 등장 순서(셀 인덱스 오름차순)로 정렬 후 occurrence번째를 고른다
  candidates.sort((a, b) => a.valueCellIdx - b.valueCellIdx);
  return candidates[occurrence - 1] ?? null;
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

    // 매치 목록 조회 — 정확 일치 실패 시 공백 폭을 바꿔가며 재시도한다.
    let matches;
    let usedQuery;
    try {
      ({ matches, usedQuery } = searchAllTextWhitespaceTolerant(doc, original));
    } catch (err) {
      process.stderr.write(`[hwp_worker] searchAllText 실패 op=${operation_id}: ${err.message}\n`);
      failed.push({ operation_id, reason: `searchAllText 오류: ${err.message}` });
      continue;
    }

    if (!Array.isArray(matches) || matches.length === 0) {
      // original이 통째로는 없지만(예: "대표자 (인)") 라벨/빈 값 셀/접미사가
      // 서로 다른 셀에 나뉘어 있는 패턴일 수 있다 — 그 경우로 한 번 더 시도한다.
      const gap = resolveLabelGapValueCell(doc, original, occurrence);
      if (gap && replacement.startsWith(gap.head) && replacement.endsWith(gap.tail)) {
        const value = replacement.slice(gap.head.length, replacement.length - gap.tail.length).trim();
        try {
          const inserted = insertValueIntoCell(doc, gap.sec, gap.parentPara, gap.ctrlIdx, gap.valueCellIdx, value);
          if (inserted) {
            applied.push(operation_id);
            process.stderr.write(
              `[hwp_worker] 라벨/빈값/접미사 분할 매칭 op=${operation_id}: "${gap.head}"…"${gap.tail}" 사이 셀에 "${value}" 삽입\n`
            );
            continue;
          }
        } catch (err) {
          process.stderr.write(`[hwp_worker] 분할 셀 삽입 오류 op=${operation_id}: ${err.message}\n`);
        }
      }

      process.stderr.write(`[hwp_worker] 텍스트 없음 op=${operation_id}: "${original}"\n`);
      failed.push({ operation_id, reason: '텍스트를 찾을 수 없습니다.' });
      continue;
    }
    if (usedQuery !== original) {
      process.stderr.write(
        `[hwp_worker] 공백 폭 보정으로 매칭 op=${operation_id}: "${original}" → "${usedQuery}"\n`
      );
    }

    // 같은 라벨 글자가 문서 안에 여러 군데(예: 진짜 입력 칸 라벨 vs 안내문
    // 속 우연한 동일 텍스트) 있을 수 있어, 안전하게 적용 가능한 매치를 앞으로
    // 오도록 재정렬한다 — occurrence(기본값 1)가 우연히 안전하지 않은 매치를
    // 집지 않도록(각 그룹 내부 순서는 유지하는 stable 정렬).
    matches = sortMatchesSafeFirst(doc, matches, original, replacement);

    // occurrence가 매치 수를 초과하면 실패로 마킹
    if (occurrence > matches.length) {
      process.stderr.write(
        `[hwp_worker] occurrence 범위 초과 op=${operation_id}: occurrence=${occurrence}, 매치=${matches.length}건\n`
      );
      failed.push({ operation_id, reason: `occurrence(${occurrence})가 매치 수(${matches.length})를 초과했습니다.` });
      continue;
    }

    // occurrence번째 매치 1건만 정밀 치환.
    // 표 셀 내부 매치(cellContext 존재)는 본문 좌표계의 replaceText로 처리하면
    // 안 된다 — m.para는 표 컨트롤을 담는 (대개 빈) 본문 문단이라, 라벨 셀은
    // 그대로 남고 빈 문단에 텍스트가 새 줄로 삽입된다. 셀 매치는 반드시
    // deleteTextInCell + insertTextInCell로 셀 안에서 치환한다.
    const m = matches[occurrence - 1];
    try {
      let ok;
      if (m.cellContext) {
        const { parentPara, ctrlIdx, cellIdx, cellPara } = m.cellContext;
        // 라벨/값 셀 쌍 구조 대응: replacement가 "라벨 + 값" 형태(원본으로 시작)이면,
        // 좁은 라벨 셀 안에서 여러 줄로 감기지 않도록 라벨 셀은 그대로 두고 값은
        // 읽기 순서상 가장 가까운 빈 칸에 넣는다. 바로 옆 칸만 보면 "열 헤더 행들 +
        // 그 아래 별도의 빈 입력 행" 구조(정부 공문서 양식에 흔함)를 놓치므로,
        // 몇 칸 떨어져 있어도 찾도록 findNearestEmptyCellForward로 넓혀 스캔한다.
        const appendedValue = replacement.startsWith(original)
          ? replacement.slice(original.length).trim()
          : '';
        const valueCellIdx = appendedValue
          ? findNearestEmptyCellForward(doc, m.sec, parentPara, ctrlIdx, cellIdx)
          : null;
        if (valueCellIdx !== null) {
          ok = insertValueIntoCell(doc, m.sec, parentPara, ctrlIdx, valueCellIdx, appendedValue);
        } else {
          const delResult = JSON.parse(
            doc.deleteTextInCell(m.sec, parentPara, ctrlIdx, cellIdx, cellPara, m.charOffset, m.length)
          );
          const insResult = JSON.parse(
            doc.insertTextInCell(m.sec, parentPara, ctrlIdx, cellIdx, cellPara, m.charOffset, replacement)
          );
          ok = delResult?.ok === true && insResult?.ok === true;
        }
      } else {
        const replaceResult = JSON.parse(
          doc.replaceText(m.sec, m.para, m.charOffset, m.length, replacement)
        );
        ok = replaceResult?.ok === true;
      }
      if (!ok) {
        process.stderr.write(`[hwp_worker] 치환 실패 op=${operation_id}\n`);
        failed.push({ operation_id, reason: '텍스트 치환이 실패를 반환했습니다.' });
        continue;
      }
      applied.push(operation_id);
      process.stderr.write(
        `[hwp_worker] 치환 성공 op=${operation_id}: "${original}"(${occurrence}번째${m.cellContext ? ', 표 셀 내부' : ''}) → "${replacement}"\n`
      );
    } catch (err) {
      process.stderr.write(`[hwp_worker] 치환 오류 op=${operation_id}: ${err.message}\n`);
      failed.push({ operation_id, reason: `치환 오류: ${err.message}` });
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
