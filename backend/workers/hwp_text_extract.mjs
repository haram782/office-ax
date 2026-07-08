/**
 * HWP 텍스트 추출 Node.js worker.
 *
 * argv[2] : HWP 파일 경로
 * stdout  : 추출된 plain text
 * stderr  : 로그 전용
 */

import initRhwp, { HwpDocument } from '../../frontend/node_modules/@rhwp/core/rhwp.js';
import { readFileSync } from 'node:fs';

function normalizeText(text) {
  return String(text || '').replace(/\s+/g, ' ').trim();
}

async function main() {
  const filePath = process.argv[2];
  if (!filePath) {
    process.stderr.write('[hwp_text_extract] 파일 경로가 없습니다.\n');
    process.exit(1);
  }

  const wasmPath = new URL(
    '../../frontend/node_modules/@rhwp/core/rhwp_bg.wasm',
    import.meta.url
  );

  try {
    const wasmBytes = readFileSync(wasmPath);
    await initRhwp({ module_or_path: wasmBytes });
  } catch (err) {
    process.stderr.write(`[hwp_text_extract] WASM 초기화 실패: ${err.message}\n`);
    process.exit(1);
  }

  let doc;
  try {
    doc = new HwpDocument(new Uint8Array(readFileSync(filePath)));
  } catch (err) {
    process.stderr.write(`[hwp_text_extract] HWP 로드 실패: ${err.message}\n`);
    process.exit(1);
  }

  const runs = [];
  try {
    const pageCount = Math.max(1, Number(doc.pageCount?.() || 1));
    for (let page = 0; page < pageCount; page += 1) {
      const layout = JSON.parse(doc.getPageTextLayout(page));
      for (const run of layout.runs || []) {
        if (run?.text) runs.push(run.text);
      }
    }
  } catch (err) {
    process.stderr.write(`[hwp_text_extract] 페이지 텍스트 추출 실패: ${err.message}\n`);
  }

  let text = normalizeText(runs.join(' '));
  if (!text) {
    try {
      text = normalizeText(doc.getTextRange(0, 0, 0, 100000));
    } catch (err) {
      process.stderr.write(`[hwp_text_extract] range 텍스트 추출 실패: ${err.message}\n`);
    }
  }

  if (!text) {
    process.exit(1);
  }
  process.stdout.write(text);
}

main().catch((err) => {
  process.stderr.write(`[hwp_text_extract] 예기치 않은 오류: ${err.message}\n${err.stack}\n`);
  process.exit(1);
});
