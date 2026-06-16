import { useMemo, useRef, useCallback, useState, useEffect } from 'react'
import initRhwp, { HwpDocument } from '@rhwp/core'
// ?url — Vite가 해당 파일을 asset으로 복사하고 실제 경로(해시 포함)를 반환
// node_modules 번들링 시 import.meta.url 기반 경로가 깨지는 문제를 우회
import rhwpWasmUrl from '@rhwp/core/rhwp_bg.wasm?url'

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
  pending: { text: '대기 중', cls: 'text-gray-400' },
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
          : 'border-gray-200 bg-white hover:border-blue-300 hover:bg-blue-50/40 shadow-sm'
        }`}
    >
      <div className="flex items-start gap-2">
        <span className="text-base flex-shrink-0 mt-0.5">{fileIcon(filename)}</span>
        <div className="min-w-0 flex-1">
          {/* 파일명 + 분석 중 스피너 한 줄 배치 */}
          <div className="flex items-center gap-1.5 min-w-0">
            <p className="text-[11px] font-semibold text-gray-700 truncate leading-tight" title={filename}>
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
          <span className="flex-shrink-0 mt-0.5 text-gray-400">
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

/** Excel snippet_data → 풀사이즈 테이블 */
function ExcelViewer({ data, filename }) {
  if (!data) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 text-gray-400">
        <span className="text-4xl">📊</span>
        <p className="text-sm">분석이 완료되면<br />교정 내역이 여기에 표시됩니다</p>
      </div>
    )
  }

  return (
    <div className="flex-1 min-h-0 overflow-auto p-4 space-y-5">
      {/* 원본 데이터 테이블 */}
      <div className="rounded-xl border border-gray-200 overflow-hidden shadow-sm">
        <div className="px-4 py-2.5 bg-gradient-to-r from-gray-50 to-white border-b border-gray-200 flex items-center gap-2">
          <span className="text-sm">📊</span>
          <span className="text-xs font-semibold text-gray-700">시트 미리보기</span>
          <span className="ml-auto text-[10px] text-gray-400">{filename}</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                {(data.headers || []).map((h, i) => (
                  <th key={i} className="px-3 py-2 text-left font-semibold text-gray-600 whitespace-nowrap">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(data.preview_rows || []).map((row, i) => (
                <tr key={i} className="border-t border-gray-100 hover:bg-blue-50/30 transition-colors">
                  {row.map((cell, j) => (
                    <td key={j} className="px-3 py-2 text-gray-700 whitespace-nowrap">
                      {typeof cell === 'number' ? cell.toLocaleString() : cell}
                    </td>
                  ))}
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
            {data.corrections.map((c, i) => (
              <div key={i} className="px-4 py-3 flex items-center gap-3">
                <span className="font-mono text-xs font-bold text-gray-500 w-10 flex-shrink-0 bg-gray-100 rounded px-1.5 py-0.5 text-center">
                  {c.cell}
                </span>
                <div className="flex-1 flex items-center gap-2 min-w-0 text-xs">
                  <span className="text-red-400 line-through truncate">{c.original}</span>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="flex-shrink-0 text-gray-400">
                    <line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>
                  </svg>
                  <span className="text-emerald-600 font-semibold truncate">{c.corrected}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

/** PDF → 풀사이즈 iframe */
function PdfViewer({ fileUrl, filename }) {
  if (!fileUrl) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 text-gray-400">
        <span className="text-4xl">📄</span>
        <p className="text-sm text-center">PDF 미리보기를 준비 중입니다…<br /><span className="text-xs">잠시 후 다시 시도해 주세요</span></p>
      </div>
    )
  }

  return (
    <iframe
      src={fileUrl}
      title={`PDF 미리보기: ${filename}`}
      className="flex-1 min-h-0 w-full border-0"
    />
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
    <div className="flex flex-col items-center justify-center h-full gap-3 text-gray-400">
      <span className="text-4xl">{icon}</span>
      <p className="text-sm font-medium text-gray-500">{format} 미리보기</p>
      <p className="text-xs text-center max-w-sm leading-relaxed px-6">{note}</p>
      <span className="text-[10px] bg-blue-50 text-blue-400 border border-blue-100 rounded-full px-3 py-1 mt-1">
        {badge}
      </span>
    </div>
  )
}

function CsvViewer({ data, filename }) {
  // snippet_data 구조가 ExcelViewer와 동일하므로 그대로 위임
  return <ExcelViewer data={data} filename={filename} />
}

function ImageViewer({ fileUrl, filename }) {
  if (!fileUrl) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 text-gray-400">
        <span className="text-4xl">🖼</span>
        <p className="text-sm text-center">이미지를 불러오는 중입니다…</p>
      </div>
    )
  }
  return (
    <div className="flex-1 min-h-0 flex items-center justify-center overflow-auto p-4 bg-gray-50/50">
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
function DocxViewer({ snippetData, filename }) {
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
      <div className="flex flex-col items-center justify-center h-full gap-3 text-gray-400">
        <span className="text-4xl">📝</span>
        <p className="text-sm text-center text-gray-500 font-medium">페이지 렌더링 결과가 없습니다</p>
        <p className="text-xs text-center max-w-xs leading-relaxed">
          LibreOffice 또는 poppler가 설치되어 있지 않거나 변환에 실패했습니다.<br />
          <code className="bg-gray-100 px-1 rounded text-[10px]">brew install --cask libreoffice poppler</code>
        </p>
      </div>
    )
  }

  /*
   * JS 측정(useEffect + clientWidth) 대신 CSS 박스 모델로 구현.
   * max-width + margin:auto 는 flex % 해석 불안정 문제가 없고,
   * HWP canvasW = min(containerW-48, naturalW) 와 동일한 결과를 낸다.
   */
  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-hidden bg-gray-200">
      {/* HwpViewer 상단 바와 동일한 스타일 */}
      <div className="flex-shrink-0 flex items-center justify-center gap-3 px-4 py-2 bg-white border-b border-gray-200">
        <span className="text-xs text-gray-600 tabular-nums">
          전체 <span className="font-semibold text-gray-700">{pageUrls.length}</span>페이지
        </span>
      </div>

      {/*
       * HWP naturalW ≈ 595px (rhwp A4 72pt 기준).
       * maxWidth 595px + margin auto 를 inline style 로 확실히 적용.
       * Tailwind 클래스로 걸었을 때 JIT 미생성 문제 우회.
       */}
      <div className="flex-1 overflow-auto p-6" style={{ background: '#e5e7eb' }}>
        <div style={{ maxWidth: '793px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {pageUrls.map((url, i) => (
            <div key={i} style={{ background: 'white', boxShadow: '0 4px 6px -1px rgba(0,0,0,.1), 0 2px 4px -2px rgba(0,0,0,.1)', borderRadius: '2px', overflow: 'hidden' }}>
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

function HwpViewer({ fileUrl, filename }) {
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
      const containerW = container.clientWidth - 48  // 패딩 여유
      const ratio = Math.min(1, containerW / naturalW)
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
      <div className="flex flex-col items-center justify-center h-full gap-3 text-gray-400">
        <span className="text-4xl">📄</span>
        <p className="text-sm text-center">분석이 완료되면<br />문서 내용이 여기에 표시됩니다</p>
      </div>
    )
  }

  // — 로딩 —
  if (status === 'loading') {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 text-gray-400">
        <span className="h-6 w-6 border-2 border-blue-400 border-t-transparent rounded-full animate-spin flex-shrink-0" />
        <span className="text-sm">WASM 엔진으로 문서 분석 중…</span>
        <span className="text-xs text-gray-300">파일이 브라우저 로컬에서 처리됩니다 (서버 미전송)</span>
      </div>
    )
  }

  // — 에러 —
  if (status === 'error') {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4 text-gray-400 px-6">
        <span className="text-4xl">⚠️</span>
        <p className="text-sm font-medium text-red-400">문서를 열지 못했습니다</p>
        {errMsg && (
          <p className="text-[11px] text-center max-w-xs bg-gray-50 border border-gray-100 rounded-lg px-3 py-2 font-mono break-all text-gray-500">
            {errMsg}
          </p>
        )}
        <p className="text-xs text-gray-400 text-center">
          파일이 손상되었거나 암호화된 HWP일 수 있습니다.<br />
          한글 프로그램에서 다시 저장 후 업로드해 주세요.
        </p>
      </div>
    )
  }

  // — 정상 렌더 —
  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-hidden bg-gray-100">
      {/* 페이지 내비게이터 */}
      <div className="flex-shrink-0 flex items-center justify-center gap-3 px-4 py-2 bg-white border-b border-gray-200">
        <button
          onClick={() => goToPage(pageNum - 1)}
          disabled={pageNum === 0}
          className="w-7 h-7 flex items-center justify-center rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
            <polyline points="15 18 9 12 15 6"/>
          </svg>
        </button>
        <span className="text-xs text-gray-600 tabular-nums">
          {pageNum + 1} <span className="text-gray-400">/ {totalPages}</span>
        </span>
        <button
          onClick={() => goToPage(pageNum + 1)}
          disabled={pageNum >= totalPages - 1}
          className="w-7 h-7 flex items-center justify-center rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
            <polyline points="9 18 15 12 9 6"/>
          </svg>
        </button>
        <span className="ml-auto text-[10px] text-gray-300 flex items-center gap-1">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
          </svg>
          로컬 처리
        </span>
      </div>

      {/* Canvas 렌더링 영역 */}
      <div ref={containerRef} className="flex-1 overflow-auto p-6 flex justify-center items-start">
        <div className="bg-white shadow-md rounded-sm overflow-hidden">
          <canvas ref={canvasRef} />
        </div>
      </div>
    </div>
  )
}

function PptxViewer({ snippetData, filename }) {
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
      <div className="flex flex-col items-center justify-center h-full gap-3 text-gray-400 px-6">
        <span className="text-4xl">📑</span>
        <p className="text-sm font-medium text-gray-500">PPTX 슬라이드 이미지를 생성하지 못했습니다</p>
        <p className="text-xs text-center text-gray-400 leading-relaxed max-w-xs">
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

  // 컨테이너 maxWidth: 뷰포트 높이에서 오버헤드(헤더·네비·썸네일·여백 ≈ 15rem)를
  // 빼고 16:9 역산한 너비와 80rem 중 작은 값 → 항상 화면 내에 맞음
  const containerMaxWidth = 'min(80rem, calc((100vh - 15rem) * 16 / 9))'

  return (
    // aspect-video로 카드 높이가 자연스럽게 결정되므로 overflow-auto로 스크롤 가능
    <div className="flex-1 min-h-0 overflow-auto bg-gray-100">
      <div
        className="mx-auto w-full px-5 py-5 flex flex-col gap-3"
        style={{ maxWidth: containerMaxWidth }}
      >

        {/* ── 슬라이드 카드 ── */}
        <div className="bg-white rounded-md shadow-lg overflow-hidden">
          {/* 상단 내비게이터 바 */}
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-100 bg-gray-50/70">
            <button
              onClick={() => goTo(current - 1)}
              disabled={current === 0}
              className="w-7 h-7 flex items-center justify-center rounded border border-gray-200 text-gray-400 hover:bg-white hover:text-gray-600 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                <polyline points="15 18 9 12 15 6"/>
              </svg>
            </button>

            <span className="text-xs font-medium text-gray-500 tabular-nums select-none">
              슬라이드&nbsp;
              <span className="text-gray-800">{current + 1}</span>
              <span className="text-gray-300"> / </span>
              <span className="text-gray-400">{slideCount}</span>
            </span>

            <button
              onClick={() => goTo(current + 1)}
              disabled={current >= slideCount - 1}
              className="w-7 h-7 flex items-center justify-center rounded border border-gray-200 text-gray-400 hover:bg-white hover:text-gray-600 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                <polyline points="9 18 15 12 9 6"/>
              </svg>
            </button>
          </div>

          {/* 16:9 슬라이드 이미지 영역 — aspect-video로 높이가 너비에서 결정됨 */}
          <div className="aspect-video relative bg-white">
            {currentUrl ? (
              imgError ? (
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-gray-400">
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
              <div className="absolute inset-0 flex items-center justify-center text-gray-300 text-sm">
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
                      : 'border-gray-200 hover:border-blue-300 hover:shadow-sm'}`}
                >
                  {url
                    ? <img src={url} alt={`${i + 1}`} className="w-full h-full object-cover" draggable={false} />
                    : <div className="w-full h-full bg-gray-100 flex items-center justify-center text-[9px] text-gray-400">{i + 1}</div>
                  }
                </button>
              )
            })}
          </div>
        )}

      </div>
    </div>
  )
}

/**
 * 확장자 → 뷰어 컴포넌트 라우터.
 * 신규 포맷 추가 시 이 함수만 수정하면 DocViewer·PreviewPage 양쪽에 반영됩니다.
 */
export function resolveViewer({ filename, fileUrl, snippetData }) {
  const ext = filename.split('.').pop().toLowerCase()

  switch (ext) {
    // ── 표 형식 (AI 교정 데이터 뷰) ─────────────────────────────────────────
    case 'xlsx':
    case 'xls':
      return <ExcelViewer data={snippetData} filename={filename} />
    case 'csv':
      return <CsvViewer data={snippetData} filename={filename} />

    // ── 페이지 문서 (iframe) ─────────────────────────────────────────────────
    case 'pdf':
      return <PdfViewer fileUrl={fileUrl} filename={filename} />

    // ── 이미지 (직접 렌더) ───────────────────────────────────────────────────
    case 'png':
    case 'jpg':
    case 'jpeg':
    case 'webp':
    case 'gif':
      return <ImageViewer fileUrl={fileUrl} filename={filename} />

    // ── 스텁 (로드맵 명시, 컴포넌트 단위로 관리) ──────────────────────────────
    case 'pptx':
    case 'ppt':
      return <PptxViewer snippetData={snippetData} filename={filename} />
    case 'docx':
    case 'doc':
      return <DocxViewer snippetData={snippetData} filename={filename} />
    case 'hwp':
    case 'hwpx':
      return <HwpViewer fileUrl={fileUrl} filename={filename} />

    default:
      return (
        <div className="flex flex-col items-center justify-center h-full gap-3 text-gray-400">
          <span className="text-4xl">🗂</span>
          <p className="text-sm">미리보기를 지원하지 않는 형식입니다</p>
          <p className="text-[11px] text-gray-300">.{ext}</p>
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
    <div className="h-full flex flex-col bg-gray-50/70">
      {/* 헤더 */}
      <div className="px-3 py-2.5 border-b border-gray-200 flex-shrink-0">
        <h2 className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">
          이 세션의 파일
        </h2>
      </div>

      {/* 파일 목록 */}
      <div className="flex-1 overflow-y-auto p-2.5 space-y-1.5">
        {fileItems.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center py-8 gap-3">
            <span className="text-3xl opacity-25">📂</span>
            <p className="text-[11px] text-gray-400 leading-relaxed">
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

    // 이미 열린 팝업이 있으면 포커스만
    if (popupRef.current && !popupRef.current.closed) {
      popupRef.current.focus()
      return
    }

    // 유저 클릭 핸들러 안에서 호출 → 팝업 차단 우회
    popupRef.current = window.open(
      '/#preview',
      'ax-preview-window',
      'width=1100,height=820,resizable=yes,scrollbars=yes,location=no,menubar=no,toolbar=no',
    )

    if (!popupRef.current) {
      // eslint-disable-next-line no-alert
      alert('팝업이 차단되었습니다. 브라우저 설정에서 이 사이트의 팝업을 허용해 주세요.')
    }
  }, [filename, fileUrl, artifactUrl, snippetData])

  return (
    <div className="h-full flex flex-col bg-white">
      {/* 뷰어 헤더 */}
      <div className="flex-shrink-0 h-10 px-4 border-b border-gray-200 flex items-center gap-2.5 bg-white">
        <span className="text-sm">{fileIcon(filename)}</span>
        <span className="text-xs font-semibold text-gray-700 truncate flex-1 min-w-0" title={filename}>
          {filename}
        </span>

        {/* 새 창으로 열기 */}
        <button
          onClick={handleOpenPopup}
          title="새 창으로 열기"
          className="flex-shrink-0 flex items-center gap-1 text-[11px] text-gray-500 hover:text-blue-600 border border-gray-200 hover:border-blue-300 rounded-lg px-2 py-1 transition-colors"
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
          className="flex-shrink-0 w-7 h-7 flex items-center justify-center rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors"
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
        const idx = messages.indexOf(userMsg)
        const assistantMsg = messages.slice(idx + 1).find(m => m.role === 'assistant')
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
