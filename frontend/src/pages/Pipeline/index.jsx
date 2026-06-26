import { useState, useEffect, useCallback, useReducer, useRef } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Ic }            from '../../components/Ic'
import { useTheme }      from '../../theme'
import { useAppModal }   from '../../components/AppModal'
import { PipelineFlow }  from './PipelineFlow'
import { StepPanel }     from './StepPanel'
import { formatRelative } from '../../utils/pipelineUtils'
import {
  getPipelineById,
  getPipelineSteps,
  getPipelineRuns,
  createPipeline,
  createStep,
  updatePipeline,
  deletePipeline,
  reorderSteps,
  deleteStep,
} from '../../api/client'

// 파이프라인 타입 배지 스타일
const PIPE = {
  A: { label: '대화형',       cls: 'bg-blue-50 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300',       icon: 'bot'   },
  B: { label: '이메일 수신형', cls: 'bg-violet-50 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300', icon: 'mail'  },
  C: { label: '스케줄링형',   cls: 'bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300',    icon: 'clock' },
}

// 신규 파이프라인 타입 선택 옵션
const PIPE_OPTIONS = [
  { type: 'A', ...PIPE.A, desc: '채팅 인터페이스에서 수동으로 실행하는 파이프라인' },
  { type: 'B', ...PIPE.B, desc: '특정 이메일 수신 시 자동으로 실행되는 파이프라인' },
  { type: 'C', ...PIPE.C, desc: '지정된 시간에 자동으로 실행되는 파이프라인'      },
]

// 신규 파이프라인 생성 시 삽입할 기본 스텝 (순차 생성 — unique_together 충돌 방지)
const INITIAL_STEPS = [
  {
    step_type: 'trigger', step_order: 1, label: '이메일 수신', description: '실행 조건을 설정하세요.',
    output_label: '수신 문서',
    config: { failPolicy: 'stop', triggerMode: 'email', email: 'inbox@office-ax.com', cron: '0 9 * * 1', fileTypes: { PDF: true, HWP: false, DOCX: false, XLSX: false } },
  },
  {
    step_type: 'rag', step_order: 2, label: '스타일 참조', description: '참조할 어투·양식 에셋을 선택하세요.',
    output_label: '컨텍스트 주입',
    config: { failPolicy: 'retry', tone: '하람_보고서_스타일', form: '회사_기획서_양식' },
  },
  {
    step_type: 'aiaction', step_order: 3, label: '문서 분석 · 보정', description: '수행할 작업을 선택하세요.',
    output_label: '보정 결과',
    config: { failPolicy: 'retry', tasks: { error: true, date: false, table: false, tone: false, pii: false } },
  },
  {
    step_type: 'output', step_order: 4, label: '최종본 생성 · 회신', description: '출력 형식과 회신 방식을 설정하세요.',
    output_label: '',
    config: { failPolicy: 'skip', format: 'PDF', autoReply: false },
  },
]

// 노드 추가 시 타입별 기본값
const STEP_DEFAULTS = {
  trigger:  { label: '이메일 수신',       description: '실행 조건을 설정하세요.',            output_label: '수신 문서',       config: { failPolicy: 'stop',  triggerMode: 'email', email: 'inbox@office-ax.com', cron: '0 9 * * 1', fileTypes: { PDF: true, HWP: false, DOCX: false, XLSX: false } } },
  rag:      { label: '스타일 참조',        description: '참조할 어투·양식 에셋을 선택하세요.', output_label: '스타일 컨텍스트', config: { failPolicy: 'retry', tone: '하람_보고서_스타일', form: '회사_기획서_양식' } },
  aiaction: { label: '문서 분석 · 보정',   description: '수행할 작업을 선택하세요.',           output_label: '보정 결과',       config: { failPolicy: 'retry', tasks: { error: true, date: false, table: false, tone: false, pii: false } } },
  output:   { label: '최종본 생성 · 회신', description: '출력 형식과 회신 방식을 설정하세요.', output_label: '',                config: { failPolicy: 'skip',  format: 'PDF', autoReply: false } },
}

// 실행기록 상태 배지 메타데이터
const RUN_STATUS = {
  success: { label: '성공',   cls: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300' },
  failed:  { label: '실패',   cls: 'bg-rose-100 text-rose-700 dark:bg-rose-500/20 dark:text-rose-300'             },
  running: { label: '진행 중', cls: 'bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-300'            },
}

/** 실행기록 단일 행 */
function RunLogRow({ run }) {
  const s  = RUN_STATUS[run.status] ?? { label: run.status, cls: 'bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400' }
  const dt = new Date(run.started_at)
  // YYYY.MM.DD HH:MM 형식
  const dtStr = `${dt.getFullYear()}.${String(dt.getMonth() + 1).padStart(2, '0')}.${String(dt.getDate()).padStart(2, '0')} ${String(dt.getHours()).padStart(2, '0')}:${String(dt.getMinutes()).padStart(2, '0')}`
  return (
    <div className="flex items-start gap-3 px-5 py-3.5">
      <span className={`shrink-0 mt-0.5 text-[11px] font-medium px-2 py-0.5 rounded-full ${s.cls}`}>{s.label}</span>
      <div className="flex-1 min-w-0">
        <div className="text-xs text-zinc-400 mb-0.5">{dtStr}</div>
        {run.log && <p className="text-xs text-zinc-600 dark:text-zinc-300 truncate">{run.log}</p>}
      </div>
    </div>
  )
}

/**
 * 파이프라인 빌더 페이지.
 * id === 'new'  → 타입 선택 오버레이 → 생성 후 해당 ID로 이동
 * id !== 'new'  → API에서 파이프라인 + 스텝 로드
 */
export default function Pipeline() {
  const navigate               = useNavigate()
  const { id }                 = useParams()
  const { theme, toggleTheme } = useTheme()
  const { showAlert, showConfirm } = useAppModal()

  // 파이프라인 데이터
  const [pipeline, setPipeline]         = useState(null)
  const [steps, setSteps]               = useState([])
  const [pipelineName, setPipelineName] = useState('새 파이프라인')

  // 이름 인라인 수정 — nameRef로 stale closure 방지
  const [nameEditing, setNameEditing]   = useState(false)
  const nameInputRef                    = useRef(null)
  const nameRef                         = useRef(pipelineName)
  useEffect(() => { nameRef.current = pipelineName }, [pipelineName])

  // UI 상태
  const [loading, setLoading]               = useState(id !== 'new')
  const [creating, setCreating]             = useState(false)
  const [saving, setSaving]                 = useState(false)
  const [saveFlash, setSaveFlash]           = useState(false)
  const [selectedStepId, setSelectedStepId] = useState(null)
  const [showGrid, setShowGrid]             = useState(true)

  // 실행기록 모달 상태
  const [showRunLog, setShowRunLog]         = useState(false)
  const [runLogs, setRunLogs]               = useState(null)   // null = 미로드
  const [runLogsLoading, setRunLogsLoading] = useState(false)

  // 저장 시각 기반 상대 시간 표시 (1분 간격 갱신)
  const [lastSavedAt, setLastSavedAt]       = useState(null)
  const [, forceUpdate] = useReducer((x) => x + 1, 0)
  useEffect(() => {
    const t = setInterval(forceUpdate, 60_000)
    return () => clearInterval(t)
  }, [forceUpdate])

  // nameEditing 활성화 시 input 포커스 + 전체 선택
  useEffect(() => {
    if (nameEditing && nameInputRef.current) {
      nameInputRef.current.focus()
      nameInputRef.current.select()
    }
  }, [nameEditing])

  // 파이프라인 + 스텝 로드 (id 변경 시 재실행)
  useEffect(() => {
    if (id === 'new') return
    setLoading(true)
    setSelectedStepId(null)
    Promise.all([getPipelineById(id), getPipelineSteps(id)])
      .then(([p, s]) => {
        setPipeline(p)
        setPipelineName(p.name)
        setSteps(s.sort((a, b) => a.step_order - b.step_order))
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [id])

  // 이름 인라인 수정 — blur 또는 Enter 시 저장
  const handleNameBlur = async () => {
    const trimmed = nameRef.current.trim()
    setNameEditing(false)
    if (!trimmed) {
      // 빈 문자열이면 원래 이름 복원
      setPipelineName(pipeline?.name || '새 파이프라인')
      return
    }
    // 변경 없으면 API 호출 생략
    if (!pipeline || trimmed === pipeline.name) return
    try {
      await updatePipeline(id, { name: trimmed })
      // 로컬 pipeline 객체에도 즉시 반영
      setPipeline((p) => ({ ...p, name: trimmed }))
    } catch {
      setPipelineName(pipeline.name)  // 실패 시 롤백
      showAlert('이름 저장에 실패했습니다.')
    }
  }

  // 신규 파이프라인 생성 (타입 선택 후 호출)
  const handleCreatePipeline = async (type) => {
    setCreating(true)
    try {
      const p = await createPipeline({ name: '새 파이프라인', type, trigger_meta: {}, is_active: true })
      // unique_together 제약으로 순차 생성
      for (const stepData of INITIAL_STEPS) {
        await createStep(p.id, stepData)
      }
      navigate(`/pipeline/${p.id}`, { replace: true })
    } catch (e) {
      console.error(e)
    } finally {
      setCreating(false)
    }
  }

  // 파이프라인 저장 (스텝 외 메타 업데이트)
  const handleSave = async () => {
    if (!pipeline) return
    setSaving(true)
    try {
      await updatePipeline(id, { name: nameRef.current })
      setLastSavedAt(new Date())
      setSaveFlash(true)
      setTimeout(() => setSaveFlash(false), 1600)
    } finally {
      setSaving(false)
    }
  }

  // 파이프라인 삭제
  const handleDeletePipeline = async () => {
    const ok = await showConfirm({
      message: `'${pipelineName}' 파이프라인을 삭제하면 모든 스텝 설정이 함께 삭제됩니다.`,
      confirmLabel: '삭제',
      danger: true,
    })
    if (!ok) return
    try {
      await deletePipeline(id)
      navigate('/', { replace: true })
    } catch {
      showAlert('삭제에 실패했습니다. 다시 시도해주세요.')
    }
  }

  // 실행기록 모달 열기 — API 호출 후 목록 표시
  const handleOpenRunLog = async () => {
    setShowRunLog(true)
    setRunLogs(null)
    setRunLogsLoading(true)
    try {
      const logs = await getPipelineRuns(id)
      setRunLogs(logs)
    } catch {
      setRunLogs([])
    } finally {
      setRunLogsLoading(false)
    }
  }

  // 스텝 재정렬 — 낙관적 업데이트 후 API 호출, 실패 시 롤백
  const handleReorder = useCallback(async (srcId, dstId) => {
    if (srcId === dstId) return
    const prev    = steps
    const srcIdx  = steps.findIndex((s) => s.id === srcId)
    const dstIdx  = steps.findIndex((s) => s.id === dstId)
    const reordered = [...steps]
    const [moved] = reordered.splice(srcIdx, 1)
    reordered.splice(dstIdx, 0, moved)
    const withOrder = reordered.map((s, i) => ({ ...s, step_order: i + 1 }))
    setSteps(withOrder)
    try {
      await reorderSteps(id, withOrder.map((s) => ({ id: s.id, step_order: s.step_order })))
    } catch {
      setSteps(prev)
    }
  }, [id, steps])

  // 스텝 추가
  const handleAddStep = useCallback(async (type) => {
    const defaults = STEP_DEFAULTS[type]
    try {
      const newStep = await createStep(id, { step_type: type, step_order: steps.length + 1, ...defaults })
      setSteps((prev) => [...prev, newStep])
      setSelectedStepId(newStep.id)
    } catch (e) {
      console.error(e)
    }
  }, [id, steps.length])

  // 스텝 삭제
  const handleDeleteStep = useCallback(async (stepId) => {
    try {
      await deleteStep(id, stepId)
      setSteps((prev) => prev.filter((s) => s.id !== stepId))
      if (selectedStepId === stepId) setSelectedStepId(null)
    } catch (e) {
      console.error(e)
    }
  }, [id, selectedStepId])

  // StepPanel 저장 완료 시 스텝 배열 업데이트
  const handleStepSave = useCallback((updated) => {
    setSteps((prev) => prev.map((s) => (s.id === updated.id ? updated : s)))
  }, [])

  // 격자 배경 패턴 (다크 모드 대응)
  const gridColor = theme === 'dark' ? 'rgba(120,120,128,.10)' : 'rgba(120,120,128,.13)'
  const gridStyle = {
    backgroundImage: `linear-gradient(${gridColor} 1px,transparent 1px),linear-gradient(90deg,${gridColor} 1px,transparent 1px)`,
    backgroundSize: '28px 28px',
  }

  const pipeType = pipeline?.type
  const pipeMeta = PIPE[pipeType]

  return (
    <div className="h-screen flex flex-col bg-zinc-100 dark:bg-zinc-950 relative">

      {/* 신규 파이프라인 타입 선택 오버레이 */}
      {id === 'new' && (
        <div className="absolute inset-0 z-50 flex items-center justify-center bg-zinc-950/60 backdrop-blur-sm">
          <div className="bg-white dark:bg-zinc-900 rounded-2xl border border-zinc-200 dark:border-zinc-800 shadow-2xl p-6 w-[480px]">
            <h2 className="text-base font-semibold text-zinc-800 dark:text-zinc-100 mb-1">파이프라인 타입 선택</h2>
            <p className="text-sm text-zinc-400 mb-5">실행 방식에 맞는 파이프라인 타입을 선택하세요.</p>
            <div className="flex flex-col gap-3">
              {PIPE_OPTIONS.map(({ type, label, icon, cls, desc }) => (
                <button
                  key={type}
                  onClick={() => handleCreatePipeline(type)}
                  disabled={creating}
                  className="flex items-center gap-4 p-4 rounded-xl border border-zinc-200 dark:border-zinc-700 hover:border-blue-300 dark:hover:border-blue-500/40 hover:bg-blue-50/40 dark:hover:bg-blue-500/5 text-left transition-colors disabled:opacity-60"
                >
                  <div className={`w-10 h-10 rounded-xl grid place-items-center ${cls} shrink-0`}>
                    <Ic name={icon} />
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-zinc-800 dark:text-zinc-100">{label}</div>
                    <div className="text-xs text-zinc-400">{desc}</div>
                  </div>
                </button>
              ))}
            </div>
            {creating && <div className="mt-4 text-center text-sm text-zinc-400">파이프라인 생성 중...</div>}
          </div>
        </div>
      )}

      {/* 파이프라인 전용 헤더 */}
      <header className="h-14 shrink-0 flex items-center gap-3 px-4 border-b border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900">

        {/* 대시보드 복귀 버튼 */}
        <button
          onClick={() => navigate('/')}
          className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-200 dark:border-zinc-700 px-3 py-1.5 text-sm text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800"
        >
          <Ic name="arrowLeft" />
          대시보드로 돌아가기
        </button>

        <div className="h-5 w-px bg-zinc-200 dark:bg-zinc-700" />

        {/* 파이프라인 이름 — 클릭 시 input 전환, blur/Enter 시 저장 */}
        <div className="flex items-center gap-2">
          <Ic name="workflow" className="w-4 h-4 text-blue-600 shrink-0" />
          {nameEditing ? (
            <input
              ref={nameInputRef}
              value={pipelineName}
              onChange={(e) => setPipelineName(e.target.value)}
              onBlur={handleNameBlur}
              onKeyDown={(e) => {
                if (e.key === 'Enter') e.currentTarget.blur()
                if (e.key === 'Escape') {
                  // 취소 — 원래 이름 복원
                  setPipelineName(pipeline?.name || pipelineName)
                  setNameEditing(false)
                }
              }}
              className="text-sm font-semibold text-zinc-800 dark:text-zinc-100 bg-transparent outline-none border-b border-blue-400 w-52"
            />
          ) : (
            <button
              onClick={() => pipeline && setNameEditing(true)}
              disabled={!pipeline}
              className="group flex items-center gap-1.5 text-sm font-semibold text-zinc-800 dark:text-zinc-100 hover:text-blue-600 dark:hover:text-blue-400 disabled:cursor-default transition-colors"
            >
              <span className="max-w-[200px] truncate">{pipelineName}</span>
              {pipeline && (
                <Ic name="pen" className="w-3.5 h-3.5 text-zinc-300 opacity-0 group-hover:opacity-100 transition-opacity shrink-0" />
              )}
            </button>
          )}
        </div>

        {/* 타입 배지 */}
        {pipeMeta && (
          <span className={`text-[11px] font-medium px-2 py-0.5 rounded-full ${pipeMeta.cls}`}>
            타입 {pipeType} · {pipeMeta.label}
          </span>
        )}

        <div className="flex-1" />

        {/* 저장 상태 표시 */}
        <div className="mr-2 min-w-[80px] text-right">
          {saveFlash
            ? <span className="inline-flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400 fade-in">
                <Ic name="check" className="w-3 h-3" />
                저장됨
              </span>
            : lastSavedAt
              ? <span className="text-xs text-zinc-400">마지막 저장 · {formatRelative(lastSavedAt)}</span>
              : null
          }
        </div>

        {/* 테마 토글 */}
        <button
          onClick={toggleTheme}
          className="w-9 h-9 grid place-items-center rounded-lg border border-zinc-200 dark:border-zinc-700 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800"
        >
          <Ic name={theme === 'dark' ? 'sun' : 'moon'} />
        </button>

        {/* 파이프라인 삭제 버튼 */}
        {pipeline && (
          <button
            onClick={handleDeletePipeline}
            className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-200 dark:border-zinc-700 px-3 h-9 text-sm text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-500/10"
          >
            <Ic name="trash" className="w-3.5 h-3.5" />
            삭제
          </button>
        )}

        {/* 실행기록 버튼 — 클릭 시 API 호출 후 모달 표시 */}
        <button
          onClick={handleOpenRunLog}
          className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-200 dark:border-zinc-700 px-3 py-1.5 text-sm text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800"
        >
          <Ic name="history" />
          실행기록
        </button>

        {/* 저장 버튼 */}
        <button
          onClick={handleSave}
          disabled={saving || !pipeline}
          className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white text-sm font-medium px-3.5 py-1.5"
        >
          <Ic name="save" />
          파이프라인 저장
        </button>
      </header>

      {/* 캔버스 + 스텝 패널 레이아웃 */}
      <div className="flex-1 flex overflow-hidden">

        {/* 캔버스 영역 */}
        <div className="flex-1 relative overflow-auto" style={showGrid ? gridStyle : {}}>

          {/* 좌상단 툴바 */}
          <div className="absolute top-4 left-4 z-10 flex items-center gap-2 pointer-events-none">
            <div className="pointer-events-auto rounded-lg bg-white/90 dark:bg-zinc-900/90 backdrop-blur border border-zinc-200 dark:border-zinc-800 px-3 h-9 shadow-sm flex items-center gap-2.5">
              <Ic name="workflow" className="w-3.5 h-3.5 text-zinc-400" />
              <span className="text-xs text-zinc-500">노드 {steps.length}개</span>
              <div className="h-4 w-px bg-zinc-200 dark:bg-zinc-700" />
              <span className="text-xs text-zinc-400">핸들을 드래그해 순서 변경</span>
            </div>
            <button
              onClick={() => setShowGrid((g) => !g)}
              className={[
                'pointer-events-auto w-9 h-9 grid place-items-center rounded-lg border transition-colors',
                showGrid
                  ? 'bg-blue-50 dark:bg-blue-500/15 border-blue-200 dark:border-blue-500/40 text-blue-600 dark:text-blue-300'
                  : 'bg-white/90 dark:bg-zinc-900/90 border-zinc-200 dark:border-zinc-800 text-zinc-400',
              ].join(' ')}
            >
              <Ic name="layout" />
            </button>
          </div>

          {/* 플로우 콘텐츠 */}
          <div className="min-h-full flex flex-col justify-center px-16 py-24">
            {loading ? (
              <div className="text-sm text-zinc-400">불러오는 중...</div>
            ) : (
              <PipelineFlow
                steps={steps}
                selectedStepId={selectedStepId}
                onSelectStep={setSelectedStepId}
                onReorder={handleReorder}
                onAddStep={handleAddStep}
                onDeleteStep={handleDeleteStep}
              />
            )}
          </div>
        </div>

        {/* 스텝 편집 패널 */}
        {selectedStepId && (() => {
          const step = steps.find((s) => s.id === selectedStepId)
          return step
            ? <StepPanel
                key={step.id}
                step={step}
                pipelineId={id}
                onSave={handleStepSave}
                onClose={() => setSelectedStepId(null)}
              />
            : null
        })()}
      </div>

      {/* 실행기록 모달 — AppModal과 별도로 로컬 state로 관리한다 (목록형) */}
      {showRunLog && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-zinc-950/50 backdrop-blur-sm">
          <div className="bg-white dark:bg-zinc-900 rounded-2xl border border-zinc-200 dark:border-zinc-800 shadow-2xl w-[560px] max-h-[70vh] flex flex-col fade-in">

            {/* 모달 헤더 */}
            <div className="shrink-0 flex items-center gap-3 px-5 h-14 border-b border-zinc-200 dark:border-zinc-800">
              <Ic name="history" className="w-4 h-4 text-zinc-400" />
              <span className="text-sm font-semibold text-zinc-800 dark:text-zinc-100 flex-1">실행기록</span>
              <button
                onClick={() => setShowRunLog(false)}
                className="w-8 h-8 grid place-items-center rounded-lg text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800"
              >
                <Ic name="x" />
              </button>
            </div>

            {/* 모달 본문 */}
            <div className="flex-1 overflow-auto">
              {runLogsLoading ? (
                // 로딩 스피너
                <div className="flex items-center justify-center py-12">
                  <div className="w-5 h-5 rounded-full border-2 border-blue-500 border-t-transparent animate-spin" />
                </div>
              ) : !runLogs || runLogs.length === 0 ? (
                // 빈 상태
                <div className="flex flex-col items-center justify-center py-12">
                  <Ic name="history" className="w-8 h-8 text-zinc-200 dark:text-zinc-700 mb-3" />
                  <p className="text-sm text-zinc-400">아직 실행 기록이 없습니다.</p>
                </div>
              ) : (
                // 실행기록 목록
                <div className="divide-y divide-zinc-100 dark:divide-zinc-800">
                  {runLogs.map((run) => <RunLogRow key={run.id} run={run} />)}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
