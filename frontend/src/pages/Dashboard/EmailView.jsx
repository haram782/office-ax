import { useEffect, useState } from 'react'
import { Ic } from '../../components/Ic'
import { getEmailInbox } from '../../api/client'

/** 상태 칩 색상 맵 */
const STATUS_CLS = {
  '분석완료':  'bg-blue-50 text-blue-600 dark:bg-blue-500/15 dark:text-blue-300',
  '보정완료':  'bg-emerald-50 text-emerald-600 dark:bg-emerald-500/15 dark:text-emerald-300',
  '검토중':    'bg-amber-50 text-amber-600 dark:bg-amber-500/15 dark:text-amber-300',
  '마스킹완료': 'bg-violet-50 text-violet-600 dark:bg-violet-500/15 dark:text-violet-300',
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
 */
export function EmailView() {
  const [all, setAll]       = useState([])
  const [filter, setFilter] = useState('all')

  useEffect(() => { getEmailInbox().then(setAll) }, [])

  const statuses = ['분석완료', '보정완료', '검토중', '마스킹완료']
  const rows     = filter === 'all' ? all : all.filter(r => r.status === filter)

  return (
    <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 overflow-hidden">
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
                  <span className="inline-flex items-center gap-1.5 text-zinc-500 dark:text-zinc-400 whitespace-nowrap">
                    <Ic name="fileText" className="w-3.5 h-3.5" />
                    {r.file}
                  </span>
                </td>
                <td className="px-4 py-3 text-zinc-400 text-xs whitespace-nowrap">{r.time}</td>
                <td className="px-4 py-3 text-right"><StatusChip label={r.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
