import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Ic } from '../../components/Ic'
import { getPipelines, deletePipeline } from '../../api/client'
import { buildMeta } from '../../utils/pipelineUtils'
import { useAppModal } from '../../components/AppModal'

/**
 * ISO 날짜 문자열을 "방금 수정 / n분 전 수정 / n시간 전 수정 / n일 전 수정" 형식으로 변환한다.
 * updated_at 필드가 없으면 null을 반환한다.
 */
function timeAgo(iso) {
  if (!iso) return null
  const diff = Date.now() - new Date(iso).getTime()
  const m    = Math.floor(diff / 60_000)
  if (m < 1)  return '방금 수정'
  if (m < 60) return `${m}분 전 수정`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}시간 전 수정`
  return `${Math.floor(h / 24)}일 전 수정`
}

// 파이프라인 타입 메타데이터
const TAG_META = {
  A: { label: '대화형',       cls: 'bg-blue-50 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300',       icon: 'bot'     },
  B: { label: '이메일 수신형', cls: 'bg-violet-50 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300', icon: 'mail'    },
  C: { label: '스케줄링형',   cls: 'bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300',    icon: 'clock'   },
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
function PipeRow({ pipeline, onClick, onDelete }) {
  const meta       = TAG_META[pipeline.type] ?? TAG_META.A
  const metaStr    = buildMeta(pipeline.type, pipeline.trigger_meta ?? {}, pipeline.last_run_at ?? null)
  // updated_at이 내려오면 수정시간을 메타 문자열 뒤에 붙인다
  const modifiedStr = timeAgo(pipeline.updated_at)

  return (
    <div className="group relative flex items-center gap-3 px-4 py-3.5 hover:bg-zinc-50 dark:hover:bg-zinc-800/60 border-b border-zinc-100 dark:border-zinc-800 last:border-0">
      {/* 클릭 영역 (삭제 버튼 제외 전체) */}
      <button onClick={onClick} className="flex items-center gap-3 flex-1 min-w-0 text-left">
        {/* 타입 아이콘 */}
        <div className="w-9 h-9 rounded-lg grid place-items-center bg-zinc-100 dark:bg-zinc-800 text-zinc-500 dark:text-zinc-400 shrink-0">
          <Ic name={meta.icon} />
        </div>

        {/* 이름 + 메타 */}
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-zinc-800 dark:text-zinc-100">{pipeline.name}</div>
          <div className="text-xs text-zinc-400 mt-0.5">
            {metaStr}
            {modifiedStr && <span className="ml-2 text-zinc-300 dark:text-zinc-600">· {modifiedStr}</span>}
          </div>
        </div>

        {/* 타입 배지 */}
        <span className={'shrink-0 text-[11px] font-medium px-2 py-0.5 rounded-full ' + meta.cls}>
          {pipeline.type} · {meta.label}
        </span>

        <span className="shrink-0 inline-flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400">
          열기 <Ic name="chevronRight" className="w-3.5 h-3.5" />
        </span>
      </button>

      {/* 삭제 버튼 — hover 시 표시 */}
      <button
        onClick={onDelete}
        className="shrink-0 w-8 h-8 grid place-items-center rounded-lg opacity-0 group-hover:opacity-100 text-zinc-300 dark:text-zinc-600 hover:bg-rose-50 dark:hover:bg-rose-500/15 hover:text-rose-500 transition-opacity"
        title="파이프라인 삭제"
      >
        <Ic name="trash" className="w-4 h-4" />
      </button>
    </div>
  )
}

/** 로딩 스켈레톤 행 */
function SkeletonRow() {
  return (
    <div className="px-4 py-3.5 border-b border-zinc-100 dark:border-zinc-800 last:border-0">
      <div className="h-14 rounded-lg bg-zinc-100 dark:bg-zinc-800 animate-pulse" />
    </div>
  )
}

/**
 * 파이프라인 목록 뷰 (대시보드 메인 콘텐츠).
 * API 응답: { id, name, type, trigger_meta, is_active, last_run_at }
 */
export function PipelinesView() {
  const navigate = useNavigate()
  const { showAlert, showConfirm } = useAppModal()
  const [all, setAll]         = useState([])
  const [filter, setFilter]   = useState('all')
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState(false)

  // 파이프라인 삭제 — AppModal confirm 후 API 호출, 목록에서 즉시 제거
  const handleDelete = async (e, id) => {
    e.stopPropagation()
    const ok = await showConfirm({
      message: '파이프라인을 삭제하면 모든 스텝 설정이 함께 삭제됩니다. 계속하시겠습니까?',
      confirmLabel: '삭제',
      danger: true,
    })
    if (!ok) return
    try {
      await deletePipeline(id)
      setAll(prev => prev.filter(p => p.id !== id))
    } catch {
      showAlert('삭제에 실패했습니다. 다시 시도해주세요.')
    }
  }

  useEffect(() => {
    setLoading(true)
    setError(false)
    getPipelines()
      .then(setAll)
      .catch(() => setError(true))
      .finally(() => setLoading(false))
  }, [])

  // 필터 적용
  const shown = filter === 'all' ? all : all.filter(p => p.type === filter)

  // 타입별 카운트
  const countOf = (t) => all.filter(p => p.type === t).length

  // 빈 상태 메시지 결정
  const emptyMsg = () => {
    if (error)           return '파이프라인을 불러오지 못했습니다. 새로고침 해주세요.'
    if (all.length === 0) return '아직 파이프라인이 없습니다. 새 파이프라인을 만들어보세요.'
    return '해당 타입의 파이프라인이 없습니다.'
  }

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

      {/* 타입 필터 바 */}
      <div className="flex flex-wrap items-center gap-1.5 px-4 py-3 border-b border-zinc-200 dark:border-zinc-800 bg-zinc-50/60 dark:bg-zinc-900/40">
        <span className="text-[11px] text-zinc-400 mr-1">타입 필터</span>
        <FilterChip active={filter === 'all'} label={`전체 ${all.length}`} onClick={() => setFilter('all')} />
        <FilterChip active={filter === 'A'}   label={`A · 대화형 ${countOf('A')}`}        onClick={() => setFilter('A')} />
        <FilterChip active={filter === 'B'}   label={`B · 이메일 수신형 ${countOf('B')}`}  onClick={() => setFilter('B')} />
        <FilterChip active={filter === 'C'}   label={`C · 스케줄링형 ${countOf('C')}`}    onClick={() => setFilter('C')} />
      </div>

      {/* 파이프라인 목록 */}
      <div>
        {loading ? (
          // 로딩 스켈레톤
          <>
            <SkeletonRow />
            <SkeletonRow />
            <SkeletonRow />
          </>
        ) : shown.length > 0 ? (
          shown.map(p => (
            <PipeRow
              key={p.id}
              pipeline={p}
              onClick={() => navigate(`/pipeline/${p.id}`)}
              onDelete={(e) => handleDelete(e, p.id)}
            />
          ))
        ) : (
          <div className={`px-4 py-12 text-center text-sm ${error ? 'text-rose-400' : 'text-zinc-400'}`}>
            {emptyMsg()}
          </div>
        )}
      </div>
    </div>
  )
}
