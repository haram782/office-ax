import { useEffect, useState } from 'react'
import { Ic } from '../../components/Ic'
import { getEmailAttachment, getEmailInbox } from '../../api/client'
import { SubViewerPopup } from '../Workspace/SubViewerPopup'

/**
 * 상태 칩 색상 맵.
 * 완료 상태(분석·보정·마스킹)는 grey로 통일해 시각적 노이즈를 줄인다.
 * 진행 중 상태(검토중)만 amber로 주의 표시한다.
 */
const STATUS_CLS = {
  '분석완료':  'bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400',
  '보정완료':  'bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400',
  '마스킹완료': 'bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400',
  '검토중':    'bg-amber-50 text-amber-600 dark:bg-amber-500/15 dark:text-amber-300',
}

function StatusChip({ label }) {
  return (
    <span className={'text-[11px] font-medium px-2 py-0.5 rounded-full ' + (STATUS_CLS[label] ?? 'bg-zinc-100 text-zinc-500')}>
      {label}
    </span>
  )
}

function FilterChip({ active, label, onClick }) {
  return (
    <button
      onClick={onClick}
      className={
        'text-xs px-2.5 py-1 rounded-full border transition-colors ' +
        (active
          ? 'border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-500/40 dark:bg-blue-500/15 dark:text-blue-300'
          : 'border-zinc-200 dark:border-zinc-700 text-zinc-500 dark:text-zinc-400 hover:bg-zinc-50 dark:hover:bg-zinc-800')
      }
    >
      {label}
    </button>
  )
}

/**
 * 이메일 수신 이력 뷰 (대시보드 메인 콘텐츠).
 * 첨부 파일명 클릭 → SubViewerPopup 열기.
 */
export function EmailView() {
  const [all, setAll]             = useState([])
  const [filter, setFilter]       = useState('all')
  const [openingId, setOpeningId] = useState(null)
  // { filename, fileUrl } | null
  const [popup, setPopup]         = useState(null)

  useEffect(() => { getEmailInbox().then(setAll) }, [])

  // InboundEmail 실제 상태 라벨과 일치시킨다 (api/client.js EMAIL_STATUS_LABELS)
  const statuses = ['수신', '처리 중', '완료', '실패']
  const rows     = filter === 'all' ? all : all.filter(r => r.status === filter)

  const openAttachment = async (row) => {
    if (!row?.id || openingId) return
    setOpeningId(row.id)
    try {
      const attachment = await getEmailAttachment(row.id)
      setPopup({
        filename: attachment.original_filename || row.file,
        fileUrl:  attachment.file_url || '',
      })
    } catch {
      setPopup({ filename: row.file, fileUrl: '' })
    } finally {
      setOpeningId(null)
    }
  }

  return (
    <>
      <div className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 overflow-hidden shadow-sm">
        {/* 패널 헤더 */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-200 dark:border-zinc-800">
          <h3 className="text-sm font-semibold text-zinc-700 dark:text-zinc-200">이메일 수신 이력</h3>
        </div>

        {/* 수신 전용 주소 배너 */}
        <div className="flex items-center gap-3 px-4 py-3.5 border-b border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900/60">
          <div className="w-9 h-9 rounded-lg bg-blue-50 dark:bg-blue-500/15 text-blue-600 dark:text-blue-300 grid place-items-center">
            <Ic name="inbox" className="w-5 h-5" />
          </div>
          <div className="flex-1">
            <div className="text-xs text-zinc-400">나의 문서 수신 전용 주소</div>
            <div className="text-sm font-semibold text-zinc-800 dark:text-zinc-100">park.sg@office-ax.com</div>
          </div>
          <button className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 hover:bg-zinc-50 dark:hover:bg-zinc-700 text-xs px-2.5 py-1.5 text-zinc-600 dark:text-zinc-300">
            <Ic name="copy" className="w-3.5 h-3.5" />
            주소 복사
          </button>
        </div>

        {/* 상태 필터 */}
        <div className="flex flex-wrap items-center gap-1.5 px-4 py-3 border-b border-zinc-200 dark:border-zinc-800 bg-zinc-50/60 dark:bg-zinc-900/40">
          <span className="text-[11px] text-zinc-400 mr-1">상태 필터</span>
          <FilterChip active={filter === 'all'} label={`전체 ${all.length}`} onClick={() => setFilter('all')} />
          {statuses.map(s => (
            <FilterChip key={s} active={filter === s} label={s} onClick={() => setFilter(s)} />
          ))}
        </div>

        {/* 테이블 */}
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-zinc-400 border-b border-zinc-200 dark:border-zinc-800">
                {['발신자', '제목', '첨부 문서', '수신', '상태'].map((col, i) => (
                  <th key={i} className={'font-medium px-4 py-2.5' + (i === 4 ? ' text-right' : '')}>{col}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className="border-b border-zinc-100 dark:border-zinc-800 last:border-0 hover:bg-zinc-50 dark:hover:bg-zinc-800/50">
                  <td className="px-4 py-3 text-zinc-600 dark:text-zinc-300 whitespace-nowrap">{r.from}</td>
                  <td className="px-4 py-3 text-zinc-800 dark:text-zinc-100 font-medium">{r.subject}</td>
                  <td className="px-4 py-3">
                    {/* 첨부 파일명 클릭 → SubViewerPopup 열기 */}
                    <button
                      onClick={() => openAttachment(r)}
                      disabled={openingId === r.id}
                      className="inline-flex items-center gap-1.5 text-blue-600 dark:text-blue-400 hover:underline whitespace-nowrap"
                    >
                      <Ic name="fileText" className="w-3.5 h-3.5" />
                      {r.file}
                      {openingId === r.id && (
                        <span className="h-3 w-3 border-[1.5px] border-blue-500 border-t-transparent rounded-full animate-spin" />
                      )}
                    </button>
                  </td>
                  <td className="px-4 py-3 text-zinc-400 text-xs whitespace-nowrap">{r.time}</td>
                  <td className="px-4 py-3 text-right"><StatusChip label={r.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* 첨부 파일 뷰어 팝업 */}
      {popup && (
        <SubViewerPopup
          filename={popup.filename}
          fileUrl={popup.fileUrl}
          title={`첨부 문서 · ${popup.filename}`}
          onClose={() => setPopup(null)}
        />
      )}
    </>
  )
}
