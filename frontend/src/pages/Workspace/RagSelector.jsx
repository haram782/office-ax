import { useRef } from 'react'
import { Ic } from '../../components/Ic'

// 선택 해제 옵션 라벨 — 빈 문자열 값으로 표현한다
const NONE_LABEL = '미지정'

// 컴포넌트 밖 정의 — 렌더마다 재마운트되는 것을 방지한다
function GroupSelect({ label, value, groups, onChange, onUploadClick }) {
  return (
    <div className="flex-1 min-w-0">
      <label className="block text-[10px] font-medium text-zinc-400 mb-1">{label}</label>
      <div className="flex items-center gap-1">
        <div className="relative flex-1 min-w-0">
          <select
            value={value}
            onChange={e => onChange(e.target.value)}
            className="w-full appearance-none rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-xs text-zinc-700 dark:text-zinc-200 pl-2.5 pr-7 py-1.5 cursor-pointer focus:outline-none focus:ring-1 focus:ring-blue-400"
          >
            <option value="">{NONE_LABEL}</option>
            {groups.map(g => <option key={g.name} value={g.name}>{g.name}</option>)}
          </select>
          <span className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-zinc-400">
            <Ic name="chevronDown" className="w-3.5 h-3.5" />
          </span>
        </div>
        {/* 자산 업로드 — 파일명(확장자 제외)이 그룹명이 된다 */}
        <button
          onClick={onUploadClick}
          title={`${label} 자산 업로드`}
          className="shrink-0 w-7 h-7 grid place-items-center rounded-lg border border-zinc-200 dark:border-zinc-700 text-zinc-400 hover:text-blue-600 hover:border-blue-300 dark:hover:text-blue-400"
        >
          <Ic name="plus" className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  )
}

/**
 * RAG 어투/양식 선택 셀렉터 (점검 발견 A-2: 하드코딩 → 실데이터).
 * 실제 RAG 자산 그룹을 옵션으로 보여주고, 선택은 채팅 전송 시
 * rag_asset_ids로 백엔드에 전달된다. + 버튼으로 새 자산을 업로드한다.
 */
export function RagSelector({
  toneGroups = [],
  formGroups = [],
  ragTone,
  ragForm,
  onToneChange,
  onFormChange,
  onUpload,
}) {
  const toneInputRef = useRef(null)
  const formInputRef = useRef(null)

  const handleFile = (kind) => (e) => {
    const file = e.target.files?.[0]
    if (file) onUpload?.(kind, file)
    e.target.value = '' // 같은 파일 재선택 허용
  }

  return (
    <div className="flex items-end gap-2 px-3 pt-3">
      <span className="shrink-0 inline-flex items-center gap-1 text-[11px] font-semibold text-blue-600 dark:text-blue-300 pb-1.5">
        <Ic name="sparkles" className="w-3.5 h-3.5" />
        RAG
      </span>
      <GroupSelect
        label="어투"
        value={ragTone}
        groups={toneGroups}
        onChange={onToneChange}
        onUploadClick={() => toneInputRef.current?.click()}
      />
      <GroupSelect
        label="양식"
        value={ragForm}
        groups={formGroups}
        onChange={onFormChange}
        onUploadClick={() => formInputRef.current?.click()}
      />
      <input ref={toneInputRef} type="file" className="hidden" accept=".docx,.hwp,.pdf,.xlsx,.csv" onChange={handleFile('tone')} />
      <input ref={formInputRef} type="file" className="hidden" accept=".docx,.hwp,.pdf,.xlsx,.csv" onChange={handleFile('form')} />
    </div>
  )
}
