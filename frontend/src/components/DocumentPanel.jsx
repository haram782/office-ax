import { useMemo, useRef, useCallback, useState, useEffect } from 'react'
import { resolveAssistantMsg } from '../utils/fileItemsUtils'
import initRhwp, { HwpDocument } from '@rhwp/core'
// ?url — Vite가 해당 파일을 asset으로 복사하고 실제 경로(해시 포함)를 반환
// node_modules 번들링 시 import.meta.url 기반 경로가 깨지는 문제를 우회
import rhwpWasmUrl from '@rhwp/core/rhwp_bg.wasm?url'
// pdfjs-dist v6 — ?url 패턴으로 Vite가 worker asset 경로(해시 포함)를 해결
import * as pdfjsLib from 'pdfjs-dist'
import pdfWorkerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
// PDF.js worker 경로 설정 — 모듈 로드 시 한 번만 실행 (WASM 패턴과 동일)
pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorkerUrl

// WASM 초기화 — 앱 전체에서 단 한 번만 실행, 명시적 URL로 번들러 이슈 방지
let _wasmReady = null
function ensureWasm() {
  if (!_wasmReady) _wasmReady = initRhwp({ module_or_path: rhwpWasmUrl })
  return _wasmReady
}

// ── 확장자 → 파일 아이콘 (FileCard·DocViewer 공용) ───────────────────────────

function fileIcon(filename) {
  const ext = filename.split('.').pop().toLowerCase()
  const map = { xlsx: '📊', xls: '📊', csv: '📋', pdf: '📄', docx: '📝', doc: '📝', pptx: '📑', ppt: '📑', hwp: '📄', hwpx: '📄', png: '🖼', jpg: '🖼', jpeg: '🖼', webp: '🖼', gif: '🖼' }
  return map[ext] ?? '🗂'
}

// ── 상태 배지 (processing 제외 — 스피너로 대체) ──────────────────────────────

const STATUS_LABEL = {
  pending: { text: '대기 중', cls: 'text-zinc-400' },
  done:    { text: '완료',    cls: 'text-emerald-500' },
  failed:  { text: '실패',    cls: 'text-red-400' },
}

// ── 내부 서브 컴포넌트 ────────────────────────────────────────────────────────

function FileCard({ id, filename, status, artifactUrl, isViewing, onClick }) {
  const isProcessing = status === 'processing'
  const badge = STATUS_LABEL[status]

  return (
    <div
      onClick={onClick}
      className={`rounded-xl border p-2.5 cursor-pointer transition-all
        ${isViewing
          ? 'border-blue-400 bg-blue-50 shadow-sm shadow-blue-100'
          : 'border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 hover:border-blue-300 hover:bg-blue-50/40 dark:hover:bg-blue-500/10 shadow-sm'
        }`}
    >
      <div className="flex items-start gap-2">
        <span className="text-base flex-shrink-0 mt-0.5">{fileIcon(filename)}</span>
        <div className="min-w-0 flex-1">
          {/* 파일명 + 분석 중 스피너 한 줄 배치 */}
          <div className="flex items-center gap-1.5 min-w-0">
            <p className="text-[11px] font-semibold text-zinc-700 dark:text-zinc-200 truncate leading-tight" title={filename}>
              {filename}
            </p>
            {isProcessing && (
              <span className="flex-shrink-0 h-3 w-3 border-[1.5px] border-blue-500 border-t-transparent rounded-full animate-spin" />
            )}
          </div>
          {/* 비처리 상태만 텍스트 배지 표시 */}
          {badge && (
            <p className={`text-[10px] mt-0.5 font-medium ${badge.cls}`}>{badge.text}</p>
          )}
        </div>
        {isViewing && (
          <span className="flex-shrink-0 mt-0.5 text-zinc-400">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round">
              <polyline points="9 18 15 12 9 6"/>
            </svg>
          </span>
        )}
      </div>
      {artifactUrl && (
        <a
          href={artifactUrl}
          download
          onClick={e => e.stopPropagation()}
          className="mt-2 flex items-center gap-1 text-[10px] text-emerald-600 hover:text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-2 py-1 transition-colors w-full"
        >
          <span>⬇</span>
          <span>보정 파일</span>
        </a>
      )}
    </div>
  )
}

// ── ExcelViewer 셀 하이라이트 헬퍼 ────────────────────────────────────────────

/** "ABC" → 0-based 컬럼 인덱스 (A=0, B=1, ..., Z=25, AA=26, ...) */
function colLetterToIndex(letters) {
  let result = 0
  for (const ch of letters.toUpperCase()) {
    result = result * 26 + (ch.charCodeAt(0) - 64)
  }
  return result - 1
}

/** "D12" → { col: 3, row: 11 } (0-based). 파싱 실패 시 null 반환 */
function parseCellAddress(cell) {
  const m = String(cell).match(/^([A-Za-z]+)(\d+)$/)
  if (!m) return null
  return { col: colLetterToIndex(m[1]), row: parseInt(m[2], 10) - 1 }
}

/** highlight + selectedHighlightId → 테이블 td/행에 적용할 Tailwind 클래스 */
function cellHighlightCls(h, selectedHighlightId) {
  if (!h) return ''
  if (h.id === selectedHighlightId) {
    return 'ring-2 ring-inset ring-blue-500 bg-blue-50 dark:bg-blue-900/20'
  }
  switch (h.status ?? 'pending') {
    case 'applied':  return 'bg-emerald-50/80 dark:bg-emerald-900/20 ring-1 ring-inset ring-emerald-300 dark:ring-emerald-700'
    case 'rejected': return 'opacity-50 bg-red-50/40 dark:bg-red-900/10 ring-1 ring-inset ring-red-200 dark:ring-red-800'
    case 'pending':  return 'bg-amber-50/80 dark:bg-amber-900/20 ring-1 ring-inset ring-amber-300 dark:ring-amber-700'
    default:         return ''
  }
}

/** highlight status → corrections 행 배경 클래스 */
function correctionRowCls(h, selectedHighlightId) {
  if (!h) return ''
  if (h.id === selectedHighlightId) {
    return 'bg-blue-50 dark:bg-blue-900/20 ring-1 ring-inset ring-blue-200 dark:ring-blue-800'
  }
  switch (h.status ?? 'pending') {
    case 'applied':  return 'bg-emerald-50/40 dark:bg-emerald-900/10'
    case 'rejected': return 'opacity-50 bg-red-50/20 dark:bg-red-900/10'
    case 'pending':  return 'bg-amber-50/30 dark:bg-amber-900/10'
    default:         return ''
  }
}

/**
 * 선택된 셀 anchor가 현재 preview_rows 범위 밖일 때 표시하는 compact notice.
 * sheet가 있으면 "Sheet1!D12" 형태로, 없으면 "D12"만 표시한다.
 */
function ExcelOutOfRangeNotice({ notice }) {
  const { anchor } = notice
  const cellRef = anchor.sheet ? `${anchor.sheet}!${anchor.cell}` : anchor.cell
  return (
    <div className="flex items-start gap-2 rounded-lg border border-blue-100 dark:border-blue-900/40 bg-blue-50 dark:bg-blue-950/30 px-3 py-2.5 text-xs text-blue-700 dark:text-blue-300">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="flex-shrink-0 mt-0.5 opacity-70">
        <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
      </svg>
      <span>
        <span className="font-mono font-semibold">{cellRef}</span>
        {`는 현재 미리보기 범위 밖입니다. 아래 수정 목록에서 확인하세요.`}
      </span>
    </div>
  )
}

function ExcelViewer({ previewData, highlights = [], selectedHighlightId = null, onSelectHighlight = null }) {
  const { filename, snippetData: data } = previewData

  // { "col:row" → highlight } — 미리보기 테이블 셀 하이라이트용
  const cellMap = useMemo(() => {
    const map = {}
    for (const h of highlights) {
      if (h.anchor?.type === 'cell' && h.anchor.cell) {
        const pos = parseCellAddress(h.anchor.cell)
        if (pos) map[`${pos.col}:${pos.row}`] = h
      }
    }
    return map
  }, [highlights])

  // { "D12" → highlight } — corrections 목록 행 하이라이트용
  const correctionCellMap = useMemo(() => {
    const map = {}
    for (const h of highlights) {
      if (h.anchor?.type === 'cell' && h.anchor.cell) {
        map[h.anchor.cell.toUpperCase()] = h
      }
    }
    return map
  }, [highlights])

  // 선택된 제안이 cell anchor이지만 현재 preview_rows 범위 밖이면 notice 표시용으로 반환
  const outOfRangeNotice = useMemo(() => {
    if (!selectedHighlightId || !data) return null
    const h = highlights.find(h => h.id === selectedHighlightId && h.anchor?.type === 'cell')
    if (!h) return null
    const pos = parseCellAddress(h.anchor.cell)
    if (!pos) return null
    const rows = data.preview_rows ?? []
    // 열 개수: headers 또는 첫 행 길이 기준
    const colCount = data.headers?.length ?? rows[0]?.length ?? 0
    // 행 또는 열이 미리보기 범위 안이면 notice 불필요
    const rowVisible = pos.row < rows.length
    const colVisible = colCount === 0 || pos.col < colCount
    if (rowVisible && colVisible) return null
    return h
  }, [selectedHighlightId, highlights, data])

  if (!data) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 text-zinc-400">
        <span className="text-4xl">📊</span>
        <p className="text-sm">분석이 완료되면<br />교정 내역이 여기에 표시됩니다</p>
      </div>
    )
  }

  return (
    <div className="flex-1 min-h-0 overflow-auto p-4 space-y-5">
      {/* 선택된 셀이 미리보기 범위 밖일 때 compact notice */}
      {outOfRangeNotice && (
        <ExcelOutOfRangeNotice notice={outOfRangeNotice} />
      )}

      {/* 원본 데이터 테이블 */}
      <div className="rounded-xl border border-zinc-200 dark:border-zinc-700 overflow-hidden shadow-sm">
        <div className="px-4 py-2.5 bg-gradient-to-r from-zinc-50 dark:from-zinc-800 to-white dark:to-zinc-900 border-b border-zinc-200 dark:border-zinc-700 flex items-center gap-2">
          <span className="text-sm">📊</span>
          <span className="text-xs font-semibold text-zinc-700 dark:text-zinc-200">시트 미리보기</span>
          <span className="ml-auto text-[10px] text-zinc-400">{filename}</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-zinc-50 dark:bg-zinc-800 border-b border-zinc-200 dark:border-zinc-700">
                {(data.headers || []).map((h, i) => (
                  <th key={i} className="px-3 py-2 text-left font-semibold text-zinc-600 dark:text-zinc-300 whitespace-nowrap">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(data.preview_rows || []).map((row, rowIdx) => (
                <tr key={rowIdx} className="border-t border-zinc-100 dark:border-zinc-800 hover:bg-blue-50/30 transition-colors">
                  {row.map((cell, colIdx) => {
                    // preview_rows[rowIdx] = Excel의 rowIdx+1 행 (헤더가 row 0, 데이터가 row 1~)
                    const matchH = cellMap[`${colIdx}:${rowIdx}`]
                    return (
                      <td
                        key={colIdx}
                        onClick={() => matchH && onSelectHighlight?.(matchH.id)}
                        className={`px-3 py-2 text-zinc-700 dark:text-zinc-200 whitespace-nowrap transition-colors
                          ${matchH ? 'cursor-pointer ' + cellHighlightCls(matchH, selectedHighlightId) : ''}
                        `}
                      >
                        {typeof cell === 'number' ? cell.toLocaleString() : cell}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* 감지된 오류 및 수정 목록 */}
      {(data.corrections || []).length > 0 && (
        <div className="rounded-xl border border-orange-100 overflow-hidden shadow-sm">
          <div className="px-4 py-2.5 bg-gradient-to-r from-orange-50 to-amber-50 border-b border-orange-100 flex items-center gap-2">
            <span className="text-sm">⚠️</span>
            <span className="text-xs font-semibold text-orange-700">
              감지 및 교정된 오류 {data.corrections.length}건
            </span>
          </div>
          <div className="divide-y divide-orange-50">
            {data.corrections.map((c, i) => {
              // corrections 항목과 highlight 매칭 — 클릭으로 제안 선택 가능
              const matchH = correctionCellMap[c.cell?.toUpperCase?.() ?? '']
              return (
                <div
                  key={i}
                  onClick={() => matchH && onSelectHighlight?.(matchH.id)}
                  className={`px-4 py-3 flex items-center gap-3 transition-colors
                    ${matchH ? 'cursor-pointer ' + correctionRowCls(matchH, selectedHighlightId) : ''}
                  `}
                >
                  <span className="font-mono text-xs font-bold text-zinc-500 dark:text-zinc-400 w-10 flex-shrink-0 bg-zinc-100 dark:bg-zinc-800 rounded px-1.5 py-0.5 text-center">
                    {c.cell}
                  </span>
                  <div className="flex-1 flex items-center gap-2 min-w-0 text-xs">
                    <span className="text-red-400 line-through truncate">{c.original}</span>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="flex-shrink-0 text-zinc-400">
                      <line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>
                    </svg>
                    <span className="text-emerald-600 font-semibold truncate">{c.corrected}</span>
                  </div>
                  {/* 제안 상태 인디케이터 */}
                  {matchH && matchH.status !== 'pending' && (
                    <span className={`flex-shrink-0 text-[10px] font-semibold
                      ${matchH.status === 'applied'  ? 'text-emerald-500' : 'text-red-400'}
                    `}>
                      {matchH.status === 'applied' ? '✓' : '✗'}
                    </span>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

/**
 * 개별 PDF 페이지 canvas.
 * pdfDoc · scale 변경 시 자동 재렌더링하고, 화면 진입 시 onVisible(pageNum)을 호출한다.
 */
function PdfPageCanvas({ pdfDoc, pageNum, scale, onVisible }) {
  const wrapperRef = useRef(null)
  const canvasRef  = useRef(null)
  const taskRef    = useRef(null)

  // 페이지 렌더링 — pdfDoc · scale 변경 시 재실행
  useEffect(() => {
    if (!pdfDoc) return
    let cancelled = false

    pdfDoc.getPage(pageNum).then(page => {
      if (cancelled) return
      // 이전 render task 취소
      taskRef.current?.cancel()

      const viewport = page.getViewport({ scale })
      const canvas   = canvasRef.current
      if (!canvas) return

      // DPR 배율로 고해상도 렌더링 (최대 2배, canvas.width 재할당 시 transform 자동 초기화)
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      canvas.width  = Math.floor(viewport.width  * dpr)
      canvas.height = Math.floor(viewport.height * dpr)
      canvas.style.width  = Math.floor(viewport.width)  + 'px'
      canvas.style.height = Math.floor(viewport.height) + 'px'

      const ctx = canvas.getContext('2d')
      ctx.scale(dpr, dpr)

      taskRef.current = page.render({ canvasContext: ctx, viewport })
      return taskRef.current.promise
    }).catch(err => {
      if (!cancelled && err?.name !== 'RenderingCancelledException') {
        console.error('[PdfViewer] 페이지 렌더링 오류 (page', pageNum, '):', err)
      }
    })

    return () => {
      cancelled = true
      taskRef.current?.cancel()
    }
  }, [pdfDoc, pageNum, scale])

  // IntersectionObserver — 뷰포트 진입 시 onVisible 호출로 현재 페이지 갱신
  useEffect(() => {
    const el = wrapperRef.current
    if (!el || !onVisible) return
    const observer = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) onVisible(pageNum) },
      { threshold: 0.3 },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [onVisible, pageNum])

  return (
    // id로 goToPage의 scrollIntoView 타깃을 지정
    <div id={`pdf-page-${pageNum}`} ref={wrapperRef} className="bg-white dark:bg-zinc-900 shadow-md rounded-sm overflow-hidden">
      <canvas ref={canvasRef} className="block" />
    </div>
  )
}

/**
 * PDF.js v6 기반 캔버스 뷰어.
 * 전체 페이지를 세로 스크롤로 표시하고 페이지 이동·줌을 지원한다.
 * 텍스트 레이어·하이라이트 오버레이는 2차 작업으로 별도 구현 예정.
 */
function PdfViewer({ previewData, highlights = [], selectedHighlightId = null, onSelectHighlight = null }) {
  const { fileUrl } = previewData

  const [pdfDoc,      setPdfDoc]      = useState(null)
  const [numPages,    setNumPages]    = useState(0)
  const [currentPage, setCurrentPage] = useState(1)
  const [scale,       setScale]       = useState(1.0)
  const [status,      setStatus]      = useState('idle')  // idle | loading | done | error
  const [errMsg,      setErrMsg]      = useState('')

  // PDF 문서 로드 — fileUrl 변경 시 이전 문서 해제 후 재로드
  useEffect(() => {
    if (!fileUrl) return
    let cancelled = false

    setPdfDoc(prev => { prev?.destroy(); return null })
    setNumPages(0)
    setCurrentPage(1)
    setErrMsg('')
    setStatus('loading')

    pdfjsLib.getDocument({ url: fileUrl }).promise
      .then(doc => {
        if (cancelled) { doc.destroy(); return }
        setPdfDoc(doc)
        setNumPages(doc.numPages)
        setStatus('done')
      })
      .catch(err => {
        if (!cancelled) {
          console.error('[PdfViewer]', err)
          setErrMsg(err?.message ?? String(err))
          setStatus('error')
        }
      })

    return () => { cancelled = true }
  }, [fileUrl])

  // 언마운트 시 PDF 문서 destroy — WASM 메모리 패턴과 동일한 정리 방식
  useEffect(() => () => { pdfDoc?.destroy() }, [pdfDoc])

  // 페이지 이동 — 대상 div로 스크롤 후 현재 페이지 상태 업데이트
  const goToPage = useCallback((n) => {
    const target = Math.max(1, Math.min(n, numPages))
    document.getElementById(`pdf-page-${target}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    setCurrentPage(target)
  }, [numPages])

  const handleVisible = useCallback((pageNum) => {
    setCurrentPage(pageNum)
  }, [])

  // ── fileUrl 없음 ──
  if (!fileUrl) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 text-zinc-400">
        <span className="text-4xl">📄</span>
        <p className="text-sm text-center">PDF 미리보기를 준비 중입니다…<br /><span className="text-xs">잠시 후 다시 시도해 주세요</span></p>
      </div>
    )
  }

  // ── 로딩 ──
  if (status === 'loading') {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 text-zinc-400">
        <span className="h-6 w-6 border-2 border-blue-400 border-t-transparent rounded-full animate-spin flex-shrink-0" />
        <span className="text-sm">PDF를 불러오는 중…</span>
      </div>
    )
  }

  // ── 에러 ──
  if (status === 'error') {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4 text-zinc-400 px-6">
        <span className="text-4xl">⚠️</span>
        <p className="text-sm font-medium text-red-400">PDF를 열지 못했습니다</p>
        {errMsg && (
          <p className="text-[11px] text-center max-w-xs bg-zinc-50 dark:bg-zinc-900 border border-zinc-100 dark:border-zinc-800 rounded-lg px-3 py-2 font-mono break-all text-zinc-500 dark:text-zinc-400">
            {errMsg}
          </p>
        )}
      </div>
    )
  }

  // ── 정상 렌더 ──
  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-hidden bg-zinc-100 dark:bg-zinc-800">
      {/* 페이지 내비게이터 + 줌 바 */}
      <div className="flex-shrink-0 flex items-center gap-3 px-4 py-2 bg-white dark:bg-zinc-900 border-b border-zinc-200 dark:border-zinc-700">
        {/* 이전 페이지 */}
        <button
          onClick={() => goToPage(currentPage - 1)}
          disabled={currentPage <= 1}
          className="w-7 h-7 flex items-center justify-center rounded-lg border border-zinc-200 dark:border-zinc-700 text-zinc-500 dark:text-zinc-400 hover:bg-zinc-50 dark:hover:bg-zinc-800 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
            <polyline points="15 18 9 12 15 6"/>
          </svg>
        </button>
        <span className="text-xs text-zinc-600 dark:text-zinc-300 tabular-nums">
          {currentPage} <span className="text-zinc-400">/ {numPages}</span>
        </span>
        {/* 다음 페이지 */}
        <button
          onClick={() => goToPage(currentPage + 1)}
          disabled={currentPage >= numPages}
          className="w-7 h-7 flex items-center justify-center rounded-lg border border-zinc-200 dark:border-zinc-700 text-zinc-500 dark:text-zinc-400 hover:bg-zinc-50 dark:hover:bg-zinc-800 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
            <polyline points="9 18 15 12 9 6"/>
          </svg>
        </button>

        {/* 구분선 */}
        <div className="h-4 w-px bg-zinc-200 dark:bg-zinc-700 mx-1" />

        {/* 줌 아웃 */}
        <button
          onClick={() => setScale(s => Math.max(0.25, +(s - 0.25).toFixed(2)))}
          disabled={scale <= 0.25}
          className="w-7 h-7 flex items-center justify-center rounded-lg border border-zinc-200 dark:border-zinc-700 text-zinc-500 dark:text-zinc-400 hover:bg-zinc-50 dark:hover:bg-zinc-800 disabled:opacity-30 disabled:cursor-not-allowed transition-colors text-base font-medium leading-none"
        >
          −
        </button>
        <span className="text-xs w-10 text-center tabular-nums text-zinc-600 dark:text-zinc-300">
          {Math.round(scale * 100)}%
        </span>
        {/* 줌 인 */}
        <button
          onClick={() => setScale(s => Math.min(3.0, +(s + 0.25).toFixed(2)))}
          disabled={scale >= 3.0}
          className="w-7 h-7 flex items-center justify-center rounded-lg border border-zinc-200 dark:border-zinc-700 text-zinc-500 dark:text-zinc-400 hover:bg-zinc-50 dark:hover:bg-zinc-800 disabled:opacity-30 disabled:cursor-not-allowed transition-colors text-base font-medium leading-none"
        >
          +
        </button>
      </div>

      {/* 전체 페이지 세로 스크롤 영역 */}
      <div className="flex-1 overflow-auto p-6 flex flex-col items-center gap-5">
        {Array.from({ length: numPages }, (_, i) => (
          <PdfPageCanvas
            key={i + 1}
            pdfDoc={pdfDoc}
            pageNum={i + 1}
            scale={scale}
            onVisible={handleVisible}
          />
        ))}
      </div>
    </div>
  )
}

// ── 향후 지원 예정 포맷 (확장 스텁) ──────────────────────────────────────────
//
// 신규 포맷 추가 순서:
//   1. 해당 스텁 함수를 실제 구현으로 교체
//   2. resolveViewer() switch 에 case 추가
//   3. 백엔드 _ALLOWED_SUFFIXES 에 확장자 추가
//   4. UserActionLog.FileType 에 값 추가 (이미 정의됨)

function FormatComingSoon({ icon, format, note, badge = '준비 중' }) {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-3 text-zinc-400">
      <span className="text-4xl">{icon}</span>
      <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400">{format} 미리보기</p>
      <p className="text-xs text-center max-w-sm leading-relaxed px-6">{note}</p>
      <span className="text-[10px] bg-blue-50 text-blue-400 border border-blue-100 rounded-full px-3 py-1 mt-1">
        {badge}
      </span>
    </div>
  )
}

function CsvViewer({ previewData, highlights = [], selectedHighlightId = null, onSelectHighlight = null }) {
  // snippet_data 구조가 ExcelViewer와 동일하므로 그대로 위임
  return <ExcelViewer previewData={previewData} highlights={highlights} selectedHighlightId={selectedHighlightId} onSelectHighlight={onSelectHighlight} />
}

function ImageViewer({ previewData, highlights = [], selectedHighlightId = null, onSelectHighlight = null }) {
  const { filename, fileUrl } = previewData

  if (!fileUrl) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 text-zinc-400">
        <span className="text-4xl">🖼</span>
        <p className="text-sm text-center">이미지를 불러오는 중입니다…</p>
      </div>
    )
  }
  return (
    <div className="flex-1 min-h-0 flex items-center justify-center overflow-auto p-4 bg-zinc-50/50 dark:bg-zinc-900/50">
      <img
        src={fileUrl}
        alt={filename}
        className="max-w-full max-h-full object-contain rounded-lg shadow-sm"
        onError={e => { e.currentTarget.style.display = 'none' }}
      />
    </div>
  )
}

// DocxViewer: LibreOffice+pdftoppm 변환 페이지 PNG → HWP 뷰어 동일 레이아웃
function DocxViewer({ previewData, highlights = [], selectedHighlightId = null, onSelectHighlight = null }) {
  const { filename, snippetData } = previewData
  const ext      = filename.split('.').pop().toLowerCase()
  const pageUrls = snippetData?.page_urls ?? []

  if (ext === 'doc') {
    return (
      <FormatComingSoon
        icon="📝"
        format="Word (.doc)"
        note="구형 .doc(97–2003) 형식은 지원되지 않습니다. Microsoft Word 또는 LibreOffice에서 .docx로 변환 후 다시 업로드해 주세요."
        badge=".docx 변환 필요"
      />
    )
  }

  if (pageUrls.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 text-zinc-400">
        <span className="text-4xl">📝</span>
        <p className="text-sm text-center text-zinc-500 dark:text-zinc-400 font-medium">페이지 렌더링 결과가 없습니다</p>
        <p className="text-xs text-center max-w-xs leading-relaxed">
          LibreOffice 또는 poppler가 설치되어 있지 않거나 변환에 실패했습니다.<br />
          <code className="bg-zinc-100 dark:bg-zinc-800 px-1 rounded text-[10px]">brew install --cask libreoffice poppler</code>
        </p>
      </div>
    )
  }

  // 선택된 highlight 중 anchor.type이 text_match인 것만 notice로 표시
  const activeNotice = selectedHighlightId
    ? (highlights.find(h => h.id === selectedHighlightId && h.anchor?.type === 'text_match') ?? null)
    : null

  /*
   * JS 측정(useEffect + clientWidth) 대신 CSS 박스 모델로 구현.
   * max-width + margin:auto 는 flex % 해석 불안정 문제가 없고,
   * HWP canvasW = min(containerW-48, naturalW) 와 동일한 결과를 낸다.
   */
  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-hidden bg-zinc-200 dark:bg-zinc-800">
      {/* HwpViewer 상단 바와 동일한 스타일 */}
      <div className="flex-shrink-0 flex items-center justify-center gap-3 px-4 py-2 bg-white dark:bg-zinc-900 border-b border-zinc-200 dark:border-zinc-700">
        <span className="text-xs text-zinc-600 dark:text-zinc-300 tabular-nums">
          전체 <span className="font-semibold text-zinc-700 dark:text-zinc-200">{pageUrls.length}</span>페이지
        </span>
      </div>

      {/* text_match 앵커 notice — 선택된 제안이 text_match일 때만 표시 */}
      {activeNotice && <TextMatchNotice notice={activeNotice} />}

      {/*
       * HWP naturalW ≈ 595px (rhwp A4 72pt 기준).
       * maxWidth 595px + margin auto 를 inline style 로 확실히 적용.
       * Tailwind 클래스로 걸었을 때 JIT 미생성 문제 우회.
       * 배경색은 dark: 클래스로 제어 — inline style에서 분리.
       */}
      <div className="flex-1 overflow-auto p-6 bg-zinc-200 dark:bg-zinc-800">
        <div style={{ maxWidth: '793px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {pageUrls.map((url, i) => (
            <div
              key={i}
              className="bg-white dark:bg-zinc-900"
              style={{ boxShadow: '0 4px 6px -1px rgba(0,0,0,.1), 0 2px 4px -2px rgba(0,0,0,.1)', borderRadius: '2px', overflow: 'hidden' }}
            >
              <img
                src={url}
                alt={`${i + 1}페이지`}
                style={{ width: '100%', height: 'auto', display: 'block' }}
                draggable={false}
              />
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// status → notice 배경/테두리/텍스트 색상 클래스 (DOCX/HWP/PPTX 공용)
const NOTICE_STATUS_CLS = {
  pending:  'bg-amber-50 dark:bg-amber-950/40 border-amber-200 dark:border-amber-700 text-amber-800 dark:text-amber-300',
  applied:  'bg-emerald-50 dark:bg-emerald-950/40 border-emerald-200 dark:border-emerald-700 text-emerald-800 dark:text-emerald-300',
  rejected: 'bg-zinc-100 dark:bg-zinc-800 border-zinc-200 dark:border-zinc-700 text-zinc-400 dark:text-zinc-500',
}

/**
 * text_match 앵커 notice 바 — HWP · DOCX 공용.
 * 좌표 하이라이트가 불가하므로 텍스트 컨텍스트와 교정 내용만 표시한다.
 */
function TextMatchNotice({ notice }) {
  const { anchor, replacement, reason, status = 'pending' } = notice
  const { target_text = '', context_before = '', context_after = '' } = anchor ?? {}
  const cls = NOTICE_STATUS_CLS[status] ?? NOTICE_STATUS_CLS.pending

  return (
    <div className={`flex-shrink-0 flex flex-col gap-1 px-4 py-2.5 border-b text-xs ${cls}`}>
      {/* 컨텍스트 미리보기 */}
      <div className="flex items-baseline gap-1 flex-wrap leading-relaxed">
        {context_before && (
          <span className="opacity-60 truncate max-w-[120px]" title={context_before}>
            …{context_before}
          </span>
        )}
        <span className="font-semibold underline underline-offset-2 decoration-dotted">
          {target_text}
        </span>
        {context_after && (
          <span className="opacity-60 truncate max-w-[120px]" title={context_after}>
            {context_after}…
          </span>
        )}
      </div>

      {/* 교정 내용 */}
      {replacement && (
        <div className="flex items-center gap-1.5">
          <span className="opacity-50 line-through text-[11px]">{target_text}</span>
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" className="opacity-50 flex-shrink-0">
            <line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>
          </svg>
          <span className="font-medium text-[11px]">{replacement}</span>
        </div>
      )}

      {/* 이유 */}
      {reason && (
        <p className="opacity-60 text-[10px] leading-relaxed line-clamp-1">{reason}</p>
      )}
    </div>
  )
}

/**
 * slide_shape 앵커 notice 바 — PPTX 전용.
 * 셰이프 좌표 하이라이트가 불가하므로 위치 라벨과 교정 내용만 표시한다.
 */
function SlideShapeNotice({ notice }) {
  const { anchor, replacement, reason, status = 'pending' } = notice
  const cls = NOTICE_STATUS_CLS[status] ?? NOTICE_STATUS_CLS.pending

  // "슬라이드 N · 셰이프 M" 또는 "슬라이드 N · 셰이프 M · 행 R · 열 C"
  const locationParts = []
  if (anchor?.slide_index != null) locationParts.push(`슬라이드 ${anchor.slide_index + 1}`)
  if (anchor?.shape_index != null) locationParts.push(`셰이프 ${anchor.shape_index + 1}`)
  if (anchor?.row_index   != null) locationParts.push(`행 ${anchor.row_index + 1}`)
  if (anchor?.col_index   != null) locationParts.push(`열 ${anchor.col_index + 1}`)
  const location = locationParts.join(' · ')

  return (
    <div className={`flex-shrink-0 flex flex-col gap-1 px-4 py-2.5 border-b text-xs ${cls}`}>
      {/* 위치 라벨 */}
      {location && (
        <span className="font-semibold opacity-80">{location}</span>
      )}

      {/* 교정 내용 */}
      {replacement && (
        <div className="flex items-center gap-1.5">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" className="opacity-50 flex-shrink-0">
            <line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>
          </svg>
          <span className="font-medium text-[11px]">{replacement}</span>
        </div>
      )}

      {/* 이유 */}
      {reason && (
        <p className="opacity-60 text-[10px] leading-relaxed line-clamp-1">{reason}</p>
      )}
    </div>
  )
}

function HwpViewer({ previewData, highlights = [], selectedHighlightId = null, onSelectHighlight = null }) {
  const { filename, fileUrl } = previewData
  const [status, setStatus]         = useState('idle')  // idle | loading | done | error
  const [totalPages, setTotalPages] = useState(0)
  const [pageNum, setPageNum]       = useState(0)
  const [errMsg, setErrMsg]         = useState('')
  const docRef       = useRef(null)
  const canvasRef    = useRef(null)
  const containerRef = useRef(null)

  // ① 파일 fetch → WASM 파싱 → 페이지 수 확인
  useEffect(() => {
    if (!fileUrl) return
    let cancelled = false
    if (docRef.current) { docRef.current.free(); docRef.current = null }
    setStatus('loading'); setPageNum(0); setTotalPages(0); setErrMsg('')

    ;(async () => {
      await ensureWasm()

      const res = await fetch(fileUrl)
      if (!res.ok) throw new Error(`파일 로드 실패 (HTTP ${res.status})`)

      const doc = new HwpDocument(new Uint8Array(await res.arrayBuffer()))
      if (cancelled) { doc.free(); return }

      const total = doc.pageCount()
      if (total === 0) throw new Error('빈 문서이거나 지원되지 않는 형식입니다')

      docRef.current = doc
      setTotalPages(total)
      setStatus('done')
    })().catch(err => {
      if (!cancelled) {
        console.error('[HwpViewer]', err)
        setErrMsg(err?.message ?? String(err))
        setStatus('error')
      }
    })

    return () => { cancelled = true }
  }, [fileUrl])

  // ② 페이지 번호 변경 → canvas에 직접 렌더링
  useEffect(() => {
    if (status !== 'done' || !docRef.current) return
    const canvas    = canvasRef.current
    const container = containerRef.current
    if (!canvas || !container) return

    try {
      // DPR 배율로 고해상도 렌더 → CSS 크기를 역산해 선명하게 표시
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      docRef.current.renderPageToCanvas(pageNum, canvas, dpr)

      // canvas.width/height 는 물리 픽셀, CSS 크기를 논리 픽셀로 역산
      const naturalW  = canvas.width  / dpr
      const naturalH  = canvas.height / dpr
      // 뷰어 영역(너비·높이) 안에 꽉 차되 넘치지 않도록 object-fit:contain 방식으로 배율 결정
      const PAD = 48
      const containerW = container.clientWidth  - PAD
      const containerH = container.clientHeight - PAD
      const ratioW = containerW / naturalW
      const ratioH = containerH / naturalH
      const ratio  = Math.min(ratioW, ratioH)
      canvas.style.width  = Math.floor(naturalW  * ratio) + 'px'
      canvas.style.height = Math.floor(naturalH  * ratio) + 'px'
      canvas.style.display = 'block'
    } catch (err) {
      console.error('[HwpViewer] canvas render:', err)
      setErrMsg(err?.message ?? '렌더링 실패')
      setStatus('error')
    }
  }, [status, pageNum])

  // ③ 언마운트 시 WASM 힙 메모리 해제
  useEffect(() => () => {
    if (docRef.current) { docRef.current.free(); docRef.current = null }
  }, [])

  const goToPage = useCallback((n) => {
    setPageNum(Math.max(0, Math.min(n, totalPages - 1)))
  }, [totalPages])

  // — 빈 상태 —
  if (!fileUrl) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 text-zinc-400">
        <span className="text-4xl">📄</span>
        <p className="text-sm text-center">분석이 완료되면<br />문서 내용이 여기에 표시됩니다</p>
      </div>
    )
  }

  // — 로딩 —
  if (status === 'loading') {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 text-zinc-400">
        <span className="h-6 w-6 border-2 border-blue-400 border-t-transparent rounded-full animate-spin flex-shrink-0" />
        <span className="text-sm">WASM 엔진으로 문서 분석 중…</span>
        <span className="text-xs text-zinc-300">파일이 브라우저 로컬에서 처리됩니다 (서버 미전송)</span>
      </div>
    )
  }

  // — 에러 —
  if (status === 'error') {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4 text-zinc-400 px-6">
        <span className="text-4xl">⚠️</span>
        <p className="text-sm font-medium text-red-400">문서를 열지 못했습니다</p>
        {errMsg && (
          <p className="text-[11px] text-center max-w-xs bg-zinc-50 dark:bg-zinc-900 border border-zinc-100 dark:border-zinc-800 rounded-lg px-3 py-2 font-mono break-all text-zinc-500 dark:text-zinc-400">
            {errMsg}
          </p>
        )}
        <p className="text-xs text-zinc-400 text-center">
          파일이 손상되었거나 암호화된 HWP일 수 있습니다.<br />
          한글 프로그램에서 다시 저장 후 업로드해 주세요.
        </p>
      </div>
    )
  }

  // 선택된 highlight 중 anchor.type이 text_match인 것만 notice로 표시
  const activeNotice = selectedHighlightId
    ? (highlights.find(h => h.id === selectedHighlightId && h.anchor?.type === 'text_match') ?? null)
    : null

  // — 정상 렌더 —
  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-hidden bg-zinc-100 dark:bg-zinc-800">
      {/* 페이지 내비게이터 */}
      <div className="flex-shrink-0 flex items-center justify-center gap-3 px-4 py-2 bg-white dark:bg-zinc-900 border-b border-zinc-200 dark:border-zinc-700">
        <button
          onClick={() => goToPage(pageNum - 1)}
          disabled={pageNum === 0}
          className="w-7 h-7 flex items-center justify-center rounded-lg border border-zinc-200 dark:border-zinc-700 text-zinc-500 dark:text-zinc-400 hover:bg-zinc-50 dark:hover:bg-zinc-800 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
            <polyline points="15 18 9 12 15 6"/>
          </svg>
        </button>
        <span className="text-xs text-zinc-600 dark:text-zinc-300 tabular-nums">
          {pageNum + 1} <span className="text-zinc-400">/ {totalPages}</span>
        </span>
        <button
          onClick={() => goToPage(pageNum + 1)}
          disabled={pageNum >= totalPages - 1}
          className="w-7 h-7 flex items-center justify-center rounded-lg border border-zinc-200 dark:border-zinc-700 text-zinc-500 dark:text-zinc-400 hover:bg-zinc-50 dark:hover:bg-zinc-800 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
            <polyline points="9 18 15 12 9 6"/>
          </svg>
        </button>
        <span className="ml-auto text-[10px] text-zinc-300 flex items-center gap-1">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
          </svg>
          로컬 처리
        </span>
      </div>

      {/* text_match 앵커 notice 바 — 선택된 제안이 text_match일 때만 표시 */}
      {activeNotice && <TextMatchNotice notice={activeNotice} />}

      {/* Canvas 렌더링 영역 */}
      <div ref={containerRef} className="flex-1 overflow-auto p-6 flex justify-center items-start">
        <div className="bg-white dark:bg-zinc-900 shadow-md rounded-sm overflow-hidden">
          <canvas ref={canvasRef} />
        </div>
      </div>
    </div>
  )
}

function PptxViewer({ previewData, highlights = [], selectedHighlightId = null, onSelectHighlight = null }) {
  const { filename, snippetData } = previewData
  const slideUrls  = snippetData?.slide_urls  ?? []
  const slideCount = snippetData?.slide_count ?? slideUrls.length
  const hasRender  = snippetData?.render_available ?? slideUrls.length > 0

  // 슬라이드별 캐시 버스팅 버전 오버라이드
  // { "2": "/media/slides/123/slide_3.png?v=1718400000" }
  const [slideVersions, setSlideVersions] = useState({})
  const [current, setCurrent]             = useState(0)
  const [imgError, setImgError]           = useState(false)

  // snippetData 교체(AI 패치 후 새 메시지 도착) 시 버전 오버라이드 병합
  useEffect(() => {
    if (!snippetData?.updated_slides) return
    setSlideVersions(prev => ({ ...prev, ...snippetData.updated_slides }))
  }, [snippetData?.updated_slides])

  // 슬라이드 전환 시 이미지 에러 상태 초기화
  useEffect(() => { setImgError(false) }, [current])

  const getSlideUrl = useCallback((idx) => {
    return slideVersions[String(idx)] ?? slideUrls[idx] ?? null
  }, [slideUrls, slideVersions])

  const goTo = useCallback((n) => {
    setCurrent(Math.max(0, Math.min(n, slideCount - 1)))
  }, [slideCount])

  // ── LibreOffice 미설치 / 렌더링 실패 ──
  if (!hasRender) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 text-zinc-400 px-6">
        <span className="text-4xl">📑</span>
        <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400">PPTX 슬라이드 이미지를 생성하지 못했습니다</p>
        <p className="text-xs text-center text-zinc-400 leading-relaxed max-w-xs">
          서버에 LibreOffice가 설치되어 있지 않거나 변환에 실패했습니다.<br />
          관리자에게 문의하거나 원본 PPTX를 직접 다운로드해 주세요.
        </p>
        <span className="text-[10px] bg-orange-50 text-orange-400 border border-orange-100 rounded-full px-3 py-1 mt-1">
          libreoffice --headless 필요
        </span>
      </div>
    )
  }

  // ── 슬라이드쇼 ──
  const currentUrl = getSlideUrl(current)

  // 선택된 highlight 중 anchor.type이 slide_shape인 것만 notice로 표시
  const activeNotice = selectedHighlightId
    ? (highlights.find(h => h.id === selectedHighlightId && h.anchor?.type === 'slide_shape') ?? null)
    : null

  // 컨테이너 maxWidth: 뷰포트 높이에서 오버헤드(헤더·네비·썸네일·여백 ≈ 15rem)를
  // 빼고 16:9 역산한 너비와 80rem 중 작은 값 → 항상 화면 내에 맞음
  const containerMaxWidth = 'min(80rem, calc((100vh - 15rem) * 16 / 9))'

  return (
    // notice를 스크롤 영역 밖 상단에 고정하기 위해 flex-col wrapper 사용
    <div className="flex-1 min-h-0 flex flex-col overflow-hidden bg-zinc-100 dark:bg-zinc-800">
      {/* slide_shape 앵커 notice — 선택된 제안이 slide_shape일 때만 표시 */}
      {activeNotice && <SlideShapeNotice notice={activeNotice} />}

      {/* aspect-video로 카드 높이가 자연스럽게 결정되므로 overflow-auto로 스크롤 가능 */}
      <div className="flex-1 min-h-0 overflow-auto">
      <div
        className="mx-auto w-full px-5 py-5 flex flex-col gap-3"
        style={{ maxWidth: containerMaxWidth }}
      >

        {/* ── 슬라이드 카드 ── */}
        <div className="bg-white dark:bg-zinc-900 rounded-md shadow-lg overflow-hidden">
          {/* 상단 내비게이터 바 */}
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-zinc-100 dark:border-zinc-800 bg-zinc-50/70 dark:bg-zinc-800/70">
            <button
              onClick={() => goTo(current - 1)}
              disabled={current === 0}
              className="w-7 h-7 flex items-center justify-center rounded border border-zinc-200 dark:border-zinc-700 text-zinc-400 hover:bg-white dark:hover:bg-zinc-700 hover:text-zinc-600 dark:hover:text-zinc-200 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                <polyline points="15 18 9 12 15 6"/>
              </svg>
            </button>

            <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400 tabular-nums select-none">
              슬라이드&nbsp;
              <span className="text-zinc-800 dark:text-zinc-100">{current + 1}</span>
              <span className="text-zinc-300"> / </span>
              <span className="text-zinc-400">{slideCount}</span>
            </span>

            <button
              onClick={() => goTo(current + 1)}
              disabled={current >= slideCount - 1}
              className="w-7 h-7 flex items-center justify-center rounded border border-zinc-200 dark:border-zinc-700 text-zinc-400 hover:bg-white dark:hover:bg-zinc-700 hover:text-zinc-600 dark:hover:text-zinc-200 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                <polyline points="9 18 15 12 9 6"/>
              </svg>
            </button>
          </div>

          {/* 16:9 슬라이드 이미지 영역 — aspect-video로 높이가 너비에서 결정됨 */}
          <div className="aspect-video relative bg-white dark:bg-zinc-900">
            {currentUrl ? (
              imgError ? (
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-zinc-400">
                  <span className="text-3xl">⚠️</span>
                  <p className="text-xs">슬라이드 이미지를 불러올 수 없습니다</p>
                </div>
              ) : (
                <img
                  key={currentUrl}
                  src={currentUrl}
                  alt={`슬라이드 ${current + 1}`}
                  className="absolute inset-0 w-full h-full object-contain"
                  onError={() => setImgError(true)}
                  draggable={false}
                />
              )
            ) : (
              <div className="absolute inset-0 flex items-center justify-center text-zinc-300 text-sm">
                슬라이드 없음
              </div>
            )}
          </div>
        </div>

        {/* ── 썸네일 스트립 — 카드와 동일한 maxWidth 컨테이너 안에 위치 ── */}
        {slideUrls.length > 1 && (
          <div className="flex gap-2 overflow-x-auto p-2 scrollbar-none">
            {slideUrls.map((_, i) => {
              const url = getSlideUrl(i)
              return (
                <button
                  key={i}
                  onClick={() => goTo(i)}
                  className={`flex-shrink-0 w-[108px] aspect-video rounded overflow-hidden border-2 transition-all
                    ${i === current
                      ? 'border-blue-500 shadow-md shadow-blue-100 scale-[1.03]'
                      : 'border-zinc-200 dark:border-zinc-700 hover:border-blue-300 hover:shadow-sm'}`}
                >
                  {url
                    ? <img src={url} alt={`${i + 1}`} className="w-full h-full object-cover" draggable={false} />
                    : <div className="w-full h-full bg-zinc-100 dark:bg-zinc-800 flex items-center justify-center text-[9px] text-zinc-400">{i + 1}</div>
                  }
                </button>
              )
            })}
          </div>
        )}

      </div>
    </div>
    </div>
  )
}

/**
 * 확장자 → 뷰어 컴포넌트 라우터.
 * 신규 포맷 추가 시 이 함수만 수정하면 DocViewer·PreviewPage 양쪽에 반영됩니다.
 *
 * @param {object} previewData            - { filename, fileUrl, snippetData, ... }
 * @param {object} [opts]                 - 하이라이트 계약 (v0: 시그니처 준비, 동작 미적용)
 * @param {Array}  [opts.highlights]      - 하이라이트 목록
 * @param {string} [opts.selectedHighlightId] - 선택된 하이라이트 ID
 * @param {Function} [opts.onSelectHighlight] - 하이라이트 선택 콜백
 */
export function resolveViewer(previewData, { highlights = [], selectedHighlightId = null, onSelectHighlight = null } = {}) {
  const { filename } = previewData
  const ext = filename.split('.').pop().toLowerCase()

  // 모든 뷰어에 공통으로 전달하는 props
  const viewerProps = { previewData, highlights, selectedHighlightId, onSelectHighlight }

  switch (ext) {
    // ── 표 형식 (AI 교정 데이터 뷰) ─────────────────────────────────────────
    case 'xlsx':
    case 'xls':
      return <ExcelViewer {...viewerProps} />
    case 'csv':
      return <CsvViewer {...viewerProps} />

    // ── 페이지 문서 (iframe) ─────────────────────────────────────────────────
    case 'pdf':
      return <PdfViewer {...viewerProps} />

    // ── 이미지 (직접 렌더) ───────────────────────────────────────────────────
    case 'png':
    case 'jpg':
    case 'jpeg':
    case 'webp':
    case 'gif':
      return <ImageViewer {...viewerProps} />

    // ── 스텁 (로드맵 명시, 컴포넌트 단위로 관리) ──────────────────────────────
    case 'pptx':
    case 'ppt':
      return <PptxViewer {...viewerProps} />
    case 'docx':
    case 'doc':
      return <DocxViewer {...viewerProps} />
    case 'hwp':
    case 'hwpx':
      return <HwpViewer {...viewerProps} />

    default:
      return (
        <div className="flex flex-col items-center justify-center h-full gap-3 text-zinc-400">
          <span className="text-4xl">🗂</span>
          <p className="text-sm">미리보기를 지원하지 않는 형식입니다</p>
          <p className="text-[11px] text-zinc-300">.{ext}</p>
        </div>
      )
  }
}

// ── 공개 컴포넌트 ─────────────────────────────────────────────────────────────

/**
 * 1열: 좁은 파일 목록 사이드바.
 * 파일 클릭 시 중앙 DocViewer가 열린다.
 */
export function FileSidebar({ fileItems, viewingFileId, onFileView }) {
  return (
    <div className="h-full flex flex-col bg-zinc-50/70 dark:bg-zinc-900/70">
      {/* 헤더 */}
      <div className="px-3 py-2.5 border-b border-zinc-200 dark:border-zinc-700 flex-shrink-0">
        <h2 className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest">
          이 세션의 파일
        </h2>
      </div>

      {/* 파일 목록 */}
      <div className="flex-1 overflow-y-auto p-2.5 space-y-1.5">
        {fileItems.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center py-8 gap-3">
            <span className="text-3xl opacity-25">📂</span>
            <p className="text-[11px] text-zinc-400 leading-relaxed">
              파일을 첨부하면<br />여기에 표시됩니다
            </p>
          </div>
        ) : (
          fileItems.map(f => (
            <FileCard
              key={f.id}
              {...f}
              isViewing={f.id === viewingFileId}
              onClick={() => onFileView(f.id)}
            />
          ))
        )}
      </div>
    </div>
  )
}

/**
 * 2열: 중앙 문서 뷰어 (전체 높이 활용).
 * Excel → 교정 테이블, PDF → iframe.
 * X 버튼 → 패널 닫기 (채팅창이 우측으로 확장).
 */
export function DocViewer({ previewData, onClose }) {
  const { filename, fileUrl, artifactUrl, snippetData } = previewData

  // 팝업 창 레퍼런스 (같은 target name으로 재사용)
  const popupRef = useRef(null)

  const handleOpenPopup = useCallback(() => {
    // 현재 데이터를 localStorage에 기록 → 팝업이 오픈 시 읽어감
    localStorage.setItem('ax_preview_data', JSON.stringify({
      filename,
      fileUrl,
      artifactUrl,
      snippetData,
      highlightedCells: [],
      updateId: Date.now(),
    }))

    // 새 탭으로 열기 (팝업 차단 우회 + 브라우저 탭 관리 편의)
    window.open('/preview', '_blank')
  }, [filename, fileUrl, artifactUrl, snippetData])

  return (
    <div className="h-full flex flex-col bg-white dark:bg-zinc-900">
      {/* 뷰어 헤더 */}
      <div className="flex-shrink-0 h-10 px-4 border-b border-zinc-200 dark:border-zinc-700 flex items-center gap-2.5 bg-white dark:bg-zinc-900">
        <span className="text-sm">{fileIcon(filename)}</span>
        <span className="text-xs font-semibold text-zinc-700 dark:text-zinc-200 truncate flex-1 min-w-0" title={filename}>
          {filename}
        </span>

        {/* 새 창으로 열기 */}
        <button
          onClick={handleOpenPopup}
          title="새 창으로 열기"
          className="flex-shrink-0 flex items-center gap-1 text-[11px] text-zinc-500 dark:text-zinc-400 hover:text-blue-600 dark:hover:text-blue-400 border border-zinc-200 dark:border-zinc-700 hover:border-blue-300 rounded-lg px-2 py-1 transition-colors"
        >
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
            <polyline points="15 3 21 3 21 9"/>
            <line x1="10" y1="14" x2="21" y2="3"/>
          </svg>
          새 창
        </button>

        {/* 보정 파일 다운로드 */}
        {artifactUrl && (
          <a
            href={artifactUrl}
            download
            className="flex-shrink-0 flex items-center gap-1 text-[11px] text-emerald-600 hover:text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-2 py-1 transition-colors"
            onClick={e => e.stopPropagation()}
          >
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
            보정 파일
          </a>
        )}

        {/* 닫기 버튼 → 채팅창 확장 */}
        <button
          onClick={onClose}
          title="뷰어 닫기"
          className="flex-shrink-0 w-7 h-7 flex items-center justify-center rounded-lg text-zinc-400 dark:text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>

      {/* 뷰어 본문 — resolveViewer() 가 확장자별 컴포넌트를 반환 */}
      <div className="flex-1 overflow-hidden flex flex-col min-h-0">
        {resolveViewer(previewData)}
      </div>
    </div>
  )
}

/**
 * 편의 훅: messages 배열에서 FileSidebar / DocViewer에 필요한 데이터 추출.
 * App.jsx에서 import하여 사용.
 */
export function useFileItems(messages) {
  return useMemo(() => {
    return messages
      .filter(m => m.role === 'user' && m.upload_log?.id)
      .reverse()
      .map(userMsg => {
        // 매칭 로직은 순수 함수로 추출 → fileItemsUtils.js 에서 단독 테스트 가능
        const assistantMsg = resolveAssistantMsg(messages, userMsg)
        return {
          id: userMsg.upload_log.id,
          filename: userMsg.upload_log.original_filename,
          fileUrl: userMsg.upload_log.file_url || '',
          status: assistantMsg
            ? 'done'
            : (userMsg._pending ? 'processing' : (userMsg.upload_log.status ?? 'processing')),
          artifactUrl: assistantMsg?.artifact_url || '',
          snippetData: assistantMsg?.snippet_data || null,
        }
      })
  }, [messages])
}
