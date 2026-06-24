import { Ic } from '../../components/Ic'

/**
 * RAG 어투/양식 선택 셀렉터.
 * WorkspaceChat 하단에 위치하며 적용할 어투와 양식을 선택한다.
 */
export function RagSelector({ ragTone, ragForm, onToneChange, onFormChange }) {
  const tones = ['하람_보고서_스타일', '팀_공문_어투', '기본 어투']
  const forms  = ['회사_기획서_양식', '표준_계약서_양식', '서식 미지정']

  function Select({ label, value, options, onChange }) {
    return (
      <div className="flex-1 min-w-0">
        <label className="block text-[10px] font-medium text-zinc-400 mb-1">{label}</label>
        <div className="relative">
          <select
            value={value}
            onChange={e => onChange(e.target.value)}
            className="w-full appearance-none rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-xs text-zinc-700 dark:text-zinc-200 pl-2.5 pr-7 py-1.5 cursor-pointer focus:outline-none focus:ring-1 focus:ring-blue-400"
          >
            {options.map(o => <option key={o} value={o}>{o}</option>)}
          </select>
          <span className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-zinc-400">
            <Ic name="chevronDown" className="w-3.5 h-3.5" />
          </span>
        </div>
      </div>
    )
  }

  return (
    <div className="flex items-end gap-2 px-3 pt-3">
      <span className="shrink-0 inline-flex items-center gap-1 text-[11px] font-semibold text-blue-600 dark:text-blue-300 pb-1.5">
        <Ic name="sparkles" className="w-3.5 h-3.5" />
        RAG
      </span>
      <Select label="어투" value={ragTone} options={tones} onChange={onToneChange} />
      <Select label="양식" value={ragForm}  options={forms}  onChange={onFormChange} />
    </div>
  )
}
