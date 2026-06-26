import { useRef, useState } from 'react'
import { Ic } from '../../components/Ic'

// 스텝 타입별 색상·아이콘 메타데이터
const TYPE_META = {
  trigger:  { label: '트리거',       icon: 'mail',     border: 'border-amber-300 dark:border-amber-500/40',     badge: 'bg-amber-100 text-amber-600 dark:bg-amber-500/20 dark:text-amber-300',           text: 'text-amber-600 dark:text-amber-300',     dot: 'bg-amber-500'   },
  rag:      { label: '스타일 / RAG', icon: 'sparkles', border: 'border-violet-300 dark:border-violet-500/40',   badge: 'bg-violet-100 text-violet-600 dark:bg-violet-500/20 dark:text-violet-300',       text: 'text-violet-600 dark:text-violet-300',   dot: 'bg-violet-500'  },
  aiaction: { label: 'AI 액션',      icon: 'bot',      border: 'border-blue-300 dark:border-blue-500/40',       badge: 'bg-blue-100 text-blue-600 dark:bg-blue-500/20 dark:text-blue-300',               text: 'text-blue-600 dark:text-blue-300',       dot: 'bg-blue-500'    },
  output:   { label: '출력',         icon: 'download', border: 'border-emerald-300 dark:border-emerald-500/40', badge: 'bg-emerald-100 text-emerald-600 dark:bg-emerald-500/20 dark:text-emerald-300',   text: 'text-emerald-600 dark:text-emerald-300', dot: 'bg-emerald-500' },
}

// AI 액션 태스크 한국어 레이블
const TASK_LABELS = {
  error: '오류 검출', date: '날짜 통일', table: '표 정렬', tone: '어투 보정', pii: 'PII 마스킹',
}

/** 스텝 설정에서 칩 목록을 계산한다 */
function getChips(step) {
  const { step_type: t, config: c } = step
  if (!c) return []

  if (t === 'trigger') {
    const files = Object.keys(c.fileTypes || {})
      .filter(k => c.fileTypes[k])
      .map(k => '.' + k.toLowerCase())
    return c.triggerMode === 'cron'
      ? ['⌁ ' + (c.cron || ''), ...files]
      : [c.email || '', ...files]
  }

  if (t === 'rag') {
    return [
      '어투 · ' + (c.tone || '').split('_').slice(0, 2).join('_'),
      '양식 · ' + (c.form || '').split('_').slice(0, 2).join('_'),
    ]
  }

  if (t === 'aiaction') {
    const active = Object.entries(c.tasks || {})
      .filter(([, v]) => v)
      .map(([k]) => TASK_LABELS[k])
    return active.length > 0 ? active : ['작업 미설정']
  }

  if (t === 'output') {
    return ['형식 · ' + (c.format || 'PDF'), c.autoReply ? '자동 회신' : '회신 안 함']
  }

  return []
}

/** 노드 카드 */
function NodeCard({
  step, idx, isSelected, isDragOver, onSelect, onDelete,
  onDragStart, onDragOver, onDragLeave, onDrop, onDragEnd,
}) {
  const meta = TYPE_META[step.step_type] ?? TYPE_META.output
  const chips = getChips(step)

  return (
    <div
      draggable
      onDragStart={onDragStart}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      onDragEnd={onDragEnd}
      onClick={onSelect}
      className={[
        'group relative w-64 shrink-0 self-stretch flex flex-col rounded-2xl border bg-white dark:bg-zinc-900 cursor-pointer transition-all select-none',
        isDragOver ? 'scale-[1.02]' : '',
        isSelected
          ? `${meta.border} ring-2 ring-blue-500 dark:ring-blue-400 shadow-md`
          : 'border-zinc-200 dark:border-zinc-800 shadow-sm hover:border-zinc-300 hover:shadow-md',
      ].join(' ')}
    >
      {/* 드래그 오버 시 왼쪽 파란 바 */}
      {isDragOver && (
        <span className="absolute -left-3 top-3 bottom-3 w-1 rounded-full bg-blue-500 pointer-events-none" />
      )}

      {/* 헤더 행 */}
      <div className={`px-3 py-2.5 border-b ${isSelected ? meta.border : 'border-zinc-100 dark:border-zinc-800'} flex items-center gap-2`}>
        <Ic name="grip" className="w-3.5 h-3.5 text-zinc-300 dark:text-zinc-600 cursor-grab shrink-0" />
        <span className={`text-[10px] font-semibold uppercase tracking-wide ${meta.text}`}>{meta.label}</span>
        <div className="flex-1" />
        <span className="text-[10px] text-zinc-300 dark:text-zinc-600">{String(idx + 1).padStart(2, '0')}</span>
        <button
          onClick={(e) => { e.stopPropagation(); onDelete() }}
          className="w-6 h-6 grid place-items-center rounded opacity-0 group-hover:opacity-100 hover:bg-rose-50 dark:hover:bg-rose-500/10 hover:text-rose-500 text-zinc-400 transition-all"
        >
          <Ic name="trash" className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* 바디 */}
      <div className="flex-1 px-3.5 py-3">
        <div className="flex items-center gap-2.5 mb-2">
          <div className={`w-9 h-9 rounded-lg grid place-items-center shrink-0 ${meta.badge}`}>
            <Ic name={meta.icon} />
          </div>
          <span className="text-sm font-semibold text-zinc-800 dark:text-zinc-100 truncate">{step.label}</span>
        </div>
        <p className="text-xs text-zinc-500 dark:text-zinc-400 leading-relaxed">{step.description}</p>
        {chips.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-3">
            {chips.map((c, i) => (
              <span key={i} className="text-[10px] px-2 py-0.5 rounded-md bg-zinc-100 dark:bg-zinc-800 text-zinc-500 dark:text-zinc-400">
                {c}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* 푸터 */}
      <div className={`px-3.5 py-2 border-t ${isSelected ? meta.border : 'border-zinc-100 dark:border-zinc-800'} flex items-center gap-1.5 text-[10px] ${meta.text}`}>
        <span className={`w-1.5 h-1.5 rounded-full ${meta.dot}`} />
        {idx === 0 ? '시작 노드' : '연결됨'}
      </div>
    </div>
  )
}

/**
 * 노드 간 커넥터 (레이블 + 화살표).
 * #3 — step.output_label 값을 받아 동적으로 표시한다.
 * reverse=true 이면 화살표 방향을 반전한다 (snake 홀수 행 대응).
 */
function Connector({ label, reverse = false }) {
  return (
    <div className="flex flex-col items-center justify-center gap-1.5 px-3 shrink-0 self-stretch">
      {label && (
        <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 text-zinc-400 whitespace-nowrap">
          {label}
        </span>
      )}
      <div className="flex items-center">
        {reverse ? (
          <>
            <Ic name="arrowLeft" className="w-4 h-4 text-zinc-400 -mr-2" />
            <div className="h-px w-9 bg-zinc-300 dark:bg-zinc-600" />
          </>
        ) : (
          <>
            <div className="h-px w-9 bg-zinc-300 dark:bg-zinc-600" />
            <Ic name="arrowRight" className="w-4 h-4 text-zinc-400 -ml-2" />
          </>
        )}
      </div>
    </div>
  )
}

/** 노드 추가 버튼 + 드롭다운 */
function AddButton({ addMenu, setAddMenu, onAddStep }) {
  const ADD_TYPES = [
    { type: 'trigger',  ...TYPE_META.trigger  },
    { type: 'rag',      ...TYPE_META.rag      },
    { type: 'aiaction', ...TYPE_META.aiaction },
    { type: 'output',   ...TYPE_META.output   },
  ]

  return (
    <div className="relative self-center">
      <button
        onClick={() => setAddMenu(m => !m)}
        className={[
          'w-44 h-[140px] rounded-2xl border-2 border-dashed flex flex-col items-center justify-center gap-2 transition-colors',
          addMenu
            ? 'border-blue-400 bg-blue-50/60 dark:bg-blue-500/10 text-blue-600'
            : 'border-zinc-300 dark:border-zinc-700 text-zinc-400 hover:border-blue-400 hover:text-blue-500',
        ].join(' ')}
      >
        <div className="w-9 h-9 rounded-xl border-2 border-dashed flex items-center justify-center">
          <Ic name="plus" />
        </div>
        <span className="text-xs font-medium">노드 추가</span>
      </button>

      {addMenu && (
        <div className="absolute left-1 top-full mt-2 z-30 w-52 rounded-xl border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 shadow-xl p-1.5">
          <div className="text-[11px] font-semibold text-zinc-400 px-2 py-1.5">노드 타입 선택</div>
          {ADD_TYPES.map(({ type, label, icon, badge }) => (
            <button
              key={type}
              onClick={() => { onAddStep(type); setAddMenu(false) }}
              className="w-full flex items-center gap-2.5 px-2 py-2 rounded-lg hover:bg-zinc-50 dark:hover:bg-zinc-800 text-left"
            >
              <div className={`w-7 h-7 rounded-lg grid place-items-center shrink-0 ${badge}`}>
                <Ic name={icon} className="w-3.5 h-3.5" />
              </div>
              <span className="text-sm text-zinc-700 dark:text-zinc-200">{label}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

/**
 * 파이프라인 플로우 — flex-wrap 자동 줄바꿈 레이아웃.
 *
 * 각 [노드 + 커넥터] 단위를 shrink-0으로 묶어 함께 줄바꿈되게 한다.
 * 컨테이너 폭이 바뀌면 브라우저 flex 엔진이 자동으로 재계산한다.
 * 노드 순서는 step_order 기준 좌→우, 위→아래로 표시된다.
 */
export function PipelineFlow({ steps, selectedStepId, onSelectStep, onReorder, onAddStep, onDeleteStep }) {
  const dragRef = useRef(null)
  const [dragOver, setDragOver] = useState(null)
  const [addMenu, setAddMenu]   = useState(false)

  const makeDragHandlers = (stepId) => ({
    onDragStart: (e) => {
      dragRef.current = stepId
      e.dataTransfer.effectAllowed = 'move'
    },
    onDragOver: (e) => {
      e.preventDefault()
      setDragOver(stepId)
    },
    onDragLeave: () => setDragOver(null),
    onDrop: (e) => {
      e.preventDefault()
      if (dragRef.current != null && dragRef.current !== stepId) {
        onReorder(dragRef.current, stepId)
      }
      dragRef.current = null
      setDragOver(null)
    },
    onDragEnd: () => {
      dragRef.current = null
      setDragOver(null)
    },
  })

  return (
    <div className="w-full">
      {/* 드롭다운 외부 클릭 감지 오버레이 */}
      {addMenu && <div className="fixed inset-0 z-20" onClick={() => setAddMenu(false)} />}

      {steps.length === 0 ? (
        // 스텝이 없을 때 빈 상태 — 추가 버튼만 표시한다
        <div className="flex items-center justify-center py-12">
          <AddButton addMenu={addMenu} setAddMenu={setAddMenu} onAddStep={onAddStep} />
        </div>
      ) : (
        // [노드 + 커넥터] 단위를 shrink-0 div로 묶어 컨테이너 폭에 따라 자동 줄바꿈한다.
        // gap-y-6은 줄바꿈 시 행 사이 세로 간격이다.
        <div className="flex flex-wrap items-stretch gap-y-6">
          {steps.map((step, idx) => (
            // shrink-0으로 묶어 [노드 + 커넥터]가 함께 줄바꿈되게 한다
            <div key={step.id} className="flex items-stretch shrink-0">
              <NodeCard
                step={step}
                idx={idx}
                isSelected={selectedStepId === step.id}
                isDragOver={dragOver === step.id}
                onSelect={() => onSelectStep(step.id)}
                onDelete={() => onDeleteStep(step.id)}
                {...makeDragHandlers(step.id)}
              />
              {/* 각 노드 뒤에 커넥터를 붙인다 — 마지막 노드도 포함 (→ AddButton) */}
              <Connector label={step.output_label || null} />
            </div>
          ))}
          <AddButton addMenu={addMenu} setAddMenu={setAddMenu} onAddStep={onAddStep} />
        </div>
      )}
    </div>
  )
}
