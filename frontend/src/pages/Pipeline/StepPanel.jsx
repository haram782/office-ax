import { useState, useEffect } from 'react'
import { Ic } from '../../components/Ic'
import { updateStep } from '../../api/client'
import { useAppModal } from '../../components/AppModal'

// PipelineFlow와 동일한 타입 메타데이터
const TYPE_META = {
  trigger:  { label: '트리거',       icon: 'mail',     badge: 'bg-amber-100 text-amber-600 dark:bg-amber-500/20 dark:text-amber-300',       text: 'text-amber-600 dark:text-amber-300'     },
  rag:      { label: '스타일 / RAG', icon: 'sparkles', badge: 'bg-violet-100 text-violet-600 dark:bg-violet-500/20 dark:text-violet-300',   text: 'text-violet-600 dark:text-violet-300'   },
  aiaction: { label: 'AI 액션',      icon: 'bot',      badge: 'bg-blue-100 text-blue-600 dark:bg-blue-500/20 dark:text-blue-300',           text: 'text-blue-600 dark:text-blue-300'       },
  output:   { label: '출력',         icon: 'download', badge: 'bg-emerald-100 text-emerald-600 dark:bg-emerald-500/20 dark:text-emerald-300', text: 'text-emerald-600 dark:text-emerald-300' },
}

// AI 액션 체크박스 항목 정의
const AIACTION_ITEMS = [
  { key: 'error', label: '오류 검출',  sub: '수식·서식 오류 자동 감지' },
  { key: 'date',  label: '날짜 통일',  sub: 'YYYY-MM-DD 형식 통일'     },
  { key: 'table', label: '표 정렬',    sub: '표 셀 정렬·병합 정리'      },
  { key: 'tone',  label: '어투 보정',  sub: 'RAG 어투로 문체 변환'      },
  { key: 'pii',   label: 'PII 마스킹', sub: '주민번호·연락처 마스킹'    },
]

// 실패 처리 정책 옵션
const FAIL_POLICIES = [
  { v: 'stop',  label: '중단',     icon: 'ban'         },
  { v: 'retry', label: '재시도',   icon: 'repeat'      },
  { v: 'skip',  label: '건너뛰기', icon: 'skipForward' },
]

const FAIL_POLICY_DESC = {
  stop:  '오류 발생 시 즉시 중단하고 담당자에게 알립니다.',
  retry: '실패 시 최대 3회까지 자동으로 재시도합니다.',
  skip:  '실패한 노드를 건너뛰고 다음 단계로 진행합니다.',
}

// ── 공통 UI 헬퍼 ────────────────────────────────────────────────────────────

/** 섹션 레이블 */
function SectionLabel({ icon, children }) {
  return (
    <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-zinc-400 mb-3">
      <Ic name={icon} className="w-3.5 h-3.5" />
      {children}
    </div>
  )
}

/** 공통 input 스타일 */
const inputCls = 'w-full h-10 rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 px-3 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-500/20 text-zinc-800 dark:text-zinc-100'

/** 공통 textarea 스타일 */
const textareaCls = 'w-full rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 px-3 py-2 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-500/20 resize-none leading-relaxed text-zinc-800 dark:text-zinc-100'

/** 세그먼트 컨트롤 (단일 선택) */
function Seg({ options, value, onChange }) {
  return (
    <div className="flex p-1 bg-zinc-100 dark:bg-zinc-800 rounded-full gap-1">
      {options.map(opt => (
        <button
          key={opt.v}
          onClick={() => onChange(opt.v)}
          className={[
            'flex-1 flex items-center justify-center gap-1.5 h-8 px-3 rounded-full text-xs font-medium transition-colors',
            value === opt.v
              ? 'bg-blue-600 text-white shadow-sm'
              : 'text-zinc-500 dark:text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200',
          ].join(' ')}
        >
          {opt.icon && <Ic name={opt.icon} className="w-3.5 h-3.5" />}
          {opt.label}
        </button>
      ))}
    </div>
  )
}

/** 체크박스 행 */
function CheckRow({ label, sub, checked, onChange }) {
  return (
    <button
      onClick={() => onChange(!checked)}
      className={[
        'w-full flex items-center gap-3 px-3 h-11 rounded-lg border text-left transition-colors',
        checked
          ? 'border-blue-200 dark:border-blue-500/40 bg-blue-50 dark:bg-blue-500/10'
          : 'border-zinc-200 dark:border-zinc-700 hover:bg-zinc-50 dark:hover:bg-zinc-800',
      ].join(' ')}
    >
      <span className={[
        'w-5 h-5 rounded-md border flex items-center justify-center shrink-0',
        checked ? 'bg-blue-600 border-blue-600 text-white' : 'border-zinc-300 dark:border-zinc-600',
      ].join(' ')}>
        {checked && <Ic name="check" className="w-3 h-3" />}
      </span>
      <div className="flex-1 min-w-0">
        <div className="text-sm text-zinc-700 dark:text-zinc-200">{label}</div>
        {sub && <div className="text-[11px] text-zinc-400">{sub}</div>}
      </div>
    </button>
  )
}

/** 단일 선택 pill 목록 */
function PillRow({ options, value, onChange }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map(opt => (
        <button
          key={opt.v}
          onClick={() => onChange(opt.v)}
          className={[
            'text-xs px-3 py-1.5 rounded-lg border transition-colors',
            value === opt.v
              ? 'border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-500/40 dark:bg-blue-500/15 dark:text-blue-300 font-medium'
              : 'border-zinc-200 dark:border-zinc-700 text-zinc-500 hover:bg-zinc-50 dark:hover:bg-zinc-800',
          ].join(' ')}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}

/** 다중 선택 pill (fileTypes 용) */
function PillToggleMulti({ options, values, onChange }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map(opt => {
        const active = values[opt]
        return (
          <button
            key={opt}
            onClick={() => onChange({ ...values, [opt]: !active })}
            className={[
              'inline-flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg border transition-colors',
              active
                ? 'border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-500/40 dark:bg-blue-500/15 dark:text-blue-300 font-medium'
                : 'border-zinc-200 dark:border-zinc-700 text-zinc-500 hover:bg-zinc-50 dark:hover:bg-zinc-800',
            ].join(' ')}
          >
            {active && <Ic name="check" className="w-3 h-3" />}
            {opt}
          </button>
        )
      })}
    </div>
  )
}

// ── 타입별 에디터 ─────────────────────────────────────────────────────────────

/** 트리거 노드 설정 에디터 */
function TriggerEditor({ cfg, setCfg }) {
  const TRIGGER_MODES = [
    { v: 'email', label: '이메일 수신', icon: 'mail'  },
    { v: 'cron',  label: '스케줄',      icon: 'clock' },
  ]

  return (
    <div className="flex flex-col gap-4">
      <div>
        <div className="text-xs text-zinc-400 mb-2">실행 방식</div>
        <Seg
          options={TRIGGER_MODES}
          value={cfg.triggerMode}
          onChange={(v) => setCfg(c => ({ ...c, triggerMode: v }))}
        />
      </div>

      {cfg.triggerMode === 'email' ? (
        <div>
          <div className="text-xs text-zinc-400 mb-1.5">수신 이메일</div>
          <input
            className={inputCls}
            value={cfg.email || ''}
            onChange={(e) => setCfg(c => ({ ...c, email: e.target.value }))}
            placeholder="inbox@office-ax.com"
          />
        </div>
      ) : (
        <div>
          <div className="text-xs text-zinc-400 mb-1.5">Cron 표현식</div>
          <input
            className={inputCls}
            value={cfg.cron || ''}
            onChange={(e) => setCfg(c => ({ ...c, cron: e.target.value }))}
            placeholder="0 9 * * 1"
          />
          <div className="text-[11px] text-zinc-400 mt-1.5">예) 매주 월요일 09:00 → 0 9 * * 1</div>
        </div>
      )}

      <div>
        <div className="text-xs text-zinc-400 mb-2">허용 파일 형식</div>
        <PillToggleMulti
          options={['PDF', 'HWP', 'DOCX', 'XLSX']}
          values={cfg.fileTypes || {}}
          onChange={(v) => setCfg(c => ({ ...c, fileTypes: v }))}
        />
      </div>
    </div>
  )
}

/** RAG/스타일 노드 설정 에디터 */
function RagEditor({ cfg, setCfg }) {
  const TONE_OPTIONS = [
    { v: '하람_보고서_스타일', label: '하람_보고서' },
    { v: '팀_공문_어투',      label: '팀_공문'      },
    { v: '기본 어투',         label: '기본'         },
  ]
  const FORM_OPTIONS = [
    { v: '회사_기획서_양식',  label: '회사_기획서' },
    { v: '표준_계약서_양식',  label: '표준_계약서' },
    { v: '서식 미지정',       label: '미지정'       },
  ]

  return (
    <div className="flex flex-col gap-4">
      <div>
        <div className="text-xs text-zinc-400 mb-2">어투 에셋</div>
        <PillRow options={TONE_OPTIONS} value={cfg.tone} onChange={(v) => setCfg(c => ({ ...c, tone: v }))} />
      </div>
      <div>
        <div className="text-xs text-zinc-400 mb-2">양식 에셋</div>
        <PillRow options={FORM_OPTIONS} value={cfg.form} onChange={(v) => setCfg(c => ({ ...c, form: v }))} />
      </div>
    </div>
  )
}

/** AI 액션 노드 설정 에디터 */
function AiActionEditor({ cfg, setCfg }) {
  const tasks = cfg.tasks || {}
  const toggle = (key) => setCfg(c => ({ ...c, tasks: { ...c.tasks, [key]: !c.tasks?.[key] } }))

  return (
    <div className="flex flex-col gap-2">
      {AIACTION_ITEMS.map(({ key, label, sub }) => (
        <CheckRow
          key={key}
          label={label}
          sub={sub}
          checked={!!tasks[key]}
          onChange={() => toggle(key)}
        />
      ))}
    </div>
  )
}

/** 출력 노드 설정 에디터 */
function OutputEditor({ cfg, setCfg }) {
  const FORMAT_OPTIONS = [
    { v: 'PDF',    label: 'PDF'    },
    { v: 'DOCX',   label: 'DOCX'   },
    { v: 'HWP',    label: 'HWP'    },
    { v: '원본 유지', label: '원본 유지' },
  ]

  return (
    <div className="flex flex-col gap-4">
      <div>
        <div className="text-xs text-zinc-400 mb-2">출력 형식</div>
        <PillRow
          options={FORMAT_OPTIONS}
          value={cfg.format}
          onChange={(v) => setCfg(c => ({ ...c, format: v }))}
        />
      </div>

      {/* 자동 회신 토글 */}
      <button
        onClick={() => setCfg(c => ({ ...c, autoReply: !c.autoReply }))}
        className={[
          'w-full flex items-center gap-3 px-3 h-12 rounded-lg border transition-colors',
          cfg.autoReply
            ? 'border-blue-200 dark:border-blue-500/40 bg-blue-50 dark:bg-blue-500/10'
            : 'border-zinc-200 dark:border-zinc-700 hover:bg-zinc-50 dark:hover:bg-zinc-800',
        ].join(' ')}
      >
        <div className={[
          'w-9 h-9 rounded-lg grid place-items-center shrink-0',
          cfg.autoReply
            ? 'bg-blue-100 text-blue-600 dark:bg-blue-500/20 dark:text-blue-300'
            : 'bg-zinc-100 text-zinc-400 dark:bg-zinc-800',
        ].join(' ')}>
          <Ic name="reply" />
        </div>
        <div className="flex-1 text-left">
          <div className="text-sm text-zinc-700 dark:text-zinc-200">자동 회신</div>
          <div className="text-[11px] text-zinc-400">완료 후 발신자에게 자동 회신</div>
        </div>
        {/* 토글 스위치 */}
        <div className={`relative w-10 h-6 rounded-full transition-colors ${cfg.autoReply ? 'bg-blue-600' : 'bg-zinc-300 dark:bg-zinc-600'}`}>
          <span className={`absolute top-0.5 w-5 h-5 rounded-full bg-white transition-all ${cfg.autoReply ? 'left-[18px]' : 'left-0.5'}`} />
        </div>
      </button>
    </div>
  )
}

/** 실패 처리 정책 에디터 */
function FailPolicyEditor({ value, onChange }) {
  return (
    <div>
      <Seg options={FAIL_POLICIES} value={value} onChange={onChange} />
      <p className="text-[11px] text-zinc-400 mt-2 leading-relaxed">
        {FAIL_POLICY_DESC[value] || ''}
      </p>
    </div>
  )
}

// ── 메인 컴포넌트 ─────────────────────────────────────────────────────────────

/**
 * 스텝 편집 패널 (우측 사이드 패널).
 * step prop이 변경되면 내부 상태를 리셋한다.
 */
export function StepPanel({ step, pipelineId, onSave, onClose }) {
  const { showAlert } = useAppModal()

  const [name,        setName]        = useState(step.label)
  const [desc,        setDesc]        = useState(step.description)
  const [cfg,         setCfg]         = useState(step.config || {})
  const [outputLabel, setOutputLabel] = useState(step.output_label || '')  // #3
  const [saving,      setSaving]      = useState(false)

  // 선택된 스텝이 바뀌면 폼을 초기화한다
  useEffect(() => {
    setName(step.label)
    setDesc(step.description)
    setCfg(step.config || {})
    setOutputLabel(step.output_label || '')
  }, [step])

  // #2 — 원본 step prop과 현재 폼 값을 비교해 변경 여부를 감지한다
  const isDirty =
    name        !== step.label               ||
    desc        !== step.description         ||
    outputLabel !== (step.output_label || '') ||
    JSON.stringify(cfg) !== JSON.stringify(step.config || {})

  const meta = TYPE_META[step.step_type] ?? TYPE_META.output

  const handleSave = async () => {
    setSaving(true)
    try {
      const updated = await updateStep(pipelineId, step.id, {
        label:        name,
        description:  desc,
        config:       cfg,
        output_label: outputLabel,   // #3
      })
      onSave(updated)
      await showAlert('저장되었습니다')  // #2
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="w-[380px] shrink-0 border-l border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 flex flex-col panel-in">
      {/* 헤더 */}
      <div className="shrink-0 flex items-center gap-2.5 px-4 h-14 border-b border-zinc-200 dark:border-zinc-800">
        <div className={`w-9 h-9 rounded-lg grid place-items-center shrink-0 ${meta.badge}`}>
          <Ic name={meta.icon} />
        </div>
        <div className="flex-1 min-w-0">
          <div className={`text-[10px] font-semibold uppercase tracking-wide ${meta.text}`}>{meta.label}</div>
          <div className="text-sm font-semibold text-zinc-800 dark:text-zinc-100 truncate">{name}</div>
        </div>
        <button
          onClick={onClose}
          className="w-8 h-8 grid place-items-center rounded-lg text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800"
        >
          <Ic name="x" />
        </button>
      </div>

      {/* 본문 */}
      <div className="flex-1 overflow-auto px-4 py-5 flex flex-col gap-6">
        {/* 기본 정보 섹션 */}
        <section>
          <SectionLabel icon="text">기본 정보</SectionLabel>
          <div className="flex flex-col gap-3">
            <input
              className={inputCls}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="노드 이름"
            />
            <textarea
              className={textareaCls}
              rows={2}
              value={desc}
              onChange={(e) => setDesc(e.target.value)}
              placeholder="노드 설명"
            />
          </div>
        </section>

        <div className="h-px bg-zinc-100 dark:bg-zinc-800" />

        {/* 타입별 설정 섹션 */}
        <section>
          <SectionLabel icon="sliders">{meta.label} 설정</SectionLabel>
          {step.step_type === 'trigger'  && <TriggerEditor  cfg={cfg} setCfg={setCfg} />}
          {step.step_type === 'rag'      && <RagEditor       cfg={cfg} setCfg={setCfg} />}
          {step.step_type === 'aiaction' && <AiActionEditor  cfg={cfg} setCfg={setCfg} />}
          {step.step_type === 'output'   && <OutputEditor    cfg={cfg} setCfg={setCfg} />}
        </section>

        {/* #3 — 다음 노드 전달 내용 (output 타입에는 커넥터가 없으므로 숨긴다) */}
        {step.step_type !== 'output' && (
          <>
            <div className="h-px bg-zinc-100 dark:bg-zinc-800" />
            <section>
              <SectionLabel icon="reply">다음 노드 전달 내용</SectionLabel>
              <input
                className={inputCls}
                value={outputLabel}
                onChange={(e) => setOutputLabel(e.target.value)}
                placeholder="예: 수신 문서, 컨텍스트 주입"
              />
              <p className="text-[11px] text-zinc-400 mt-1.5 leading-relaxed">
                이 노드가 다음 노드로 전달하는 데이터를 한 줄로 표현합니다.
              </p>
            </section>
          </>
        )}

        <div className="h-px bg-zinc-100 dark:bg-zinc-800" />

        {/* 실패 처리 정책 섹션 */}
        <section>
          <SectionLabel icon="alert">실패 처리 정책</SectionLabel>
          <FailPolicyEditor
            value={cfg.failPolicy || 'stop'}
            onChange={(v) => setCfg(c => ({ ...c, failPolicy: v }))}
          />
        </section>
      </div>

      {/* 푸터 */}
      <div className="shrink-0 border-t border-zinc-200 dark:border-zinc-800 p-3">
        {/* #2 — 변경사항이 없을 때는 버튼을 흐리게 표시해 저장 필요 여부를 암시한다 */}
        <button
          onClick={handleSave}
          disabled={saving || !isDirty}
          className={[
            'w-full h-11 rounded-lg text-white text-sm font-medium transition-colors',
            isDirty && !saving
              ? 'bg-blue-600 hover:bg-blue-700'
              : 'bg-blue-400 opacity-60 cursor-not-allowed',
          ].join(' ')}
        >
          {saving ? '저장 중...' : isDirty ? '변경사항 저장' : '저장됨'}
        </button>
      </div>
    </div>
  )
}
