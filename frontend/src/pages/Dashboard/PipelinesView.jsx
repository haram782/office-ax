import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Ic } from '../../components/Ic'
import { getPipelines } from '../../api/client'

// 파이프라인 타입 메타데이터
const TAG_META = {
  A: { label: '대화형',      cls: 'bg-blue-50 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300',     icon: 'bot'     },
  B: { label: '이메일 수신형', cls: 'bg-violet-50 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300', icon: 'mail'    },
  C: { label: '스케줄링형',   cls: 'bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300',  icon: 'history' },
}

/** 필터 칩 */
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

/** 파이프라인 행 */
function PipeRow({ pipeline, onClick }) {
  const lead = TAG_META[pipeline.tags[0]]
  return (
    <button
      onClick={onClick}
      className="w-full text-left flex items-center gap-3 px-4 py-3.5 hover:bg-zinc-50 dark:hover:bg-zinc-800/60 border-b border-zinc-100 dark:border-zinc-800 last:border-0"
    >
      {/* 타입 아이콘 */}
      <div className="w-9 h-9 rounded-lg grid place-items-center bg-zinc-100 dark:bg-zinc-800 text-zinc-500 dark:text-zinc-400 shrink-0">
        <Ic name={lead.icon} />
      </div>
      {/* 이름 + 메타 */}
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium text-zinc-800 dark:text-zinc-100">{pipeline.name}</div>
        <div className="text-xs text-zinc-400 mt-0.5">{pipeline.meta}</div>
      </div>
      {/* 태그 배지 */}
      <div className="shrink-0 flex items-center gap-1">
        {pipeline.tags.map(t => {
          const m = TAG_META[t]
          return (
            <span key={t} className={'text-[11px] font-medium px-2 py-0.5 rounded-full ' + m.cls}>
              {t} · {m.label}
            </span>
          )
        })}
      </div>
      <span className="shrink-0 inline-flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400">
        열기 <Ic name="chevronRight" className="w-3.5 h-3.5" />
      </span>
    </button>
  )
}

/**
 * 파이프라인 목록 뷰 (대시보드 메인 콘텐츠).
 */
export function PipelinesView() {
  const navigate  = useNavigate()
  const [all, setAll]       = useState([])
  const [filter, setFilter] = useState('all')

  useEffect(() => { getPipelines().then(setAll) }, [])

  const shown = filter === 'all' ? all : all.filter(p => p.tags.includes(filter))

  return (
    <div className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 overflow-hidden shadow-sm">
      {/* 패널 헤더 */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-200 dark:border-zinc-800">
        <h3 className="text-sm font-semibold text-zinc-700 dark:text-zinc-200">나의 파이프라인</h3>
        <button
          onClick={() => navigate('/pipeline/new')}
          className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium px-3 py-1.5"
        >
          <Ic name="plus" className="w-3.5 h-3.5" />
          새 파이프라인
        </button>
      </div>

      {/* 태그 필터 바 */}
      <div className="flex flex-wrap items-center gap-1.5 px-4 py-3 border-b border-zinc-200 dark:border-zinc-800 bg-zinc-50/60 dark:bg-zinc-900/40">
        <span className="text-[11px] text-zinc-400 mr-1">태그 필터</span>
        <FilterChip active={filter === 'all'} label={`전체 ${all.length}`} onClick={() => setFilter('all')} />
        <FilterChip active={filter === 'A'}   label="A · 대화형"       onClick={() => setFilter('A')} />
        <FilterChip active={filter === 'B'}   label="B · 이메일 수신형" onClick={() => setFilter('B')} />
        <FilterChip active={filter === 'C'}   label="C · 스케줄링형"   onClick={() => setFilter('C')} />
      </div>

      {/* 파이프라인 목록 */}
      <div>
        {shown.length > 0
          ? shown.map(p => (
              <PipeRow key={p.id} pipeline={p} onClick={() => navigate(`/pipeline/${p.id}`)} />
            ))
          : (
            <div className="px-4 py-12 text-center text-sm text-zinc-400">
              해당 태그의 파이프라인이 없습니다.
            </div>
          )
        }
      </div>
    </div>
  )
}
