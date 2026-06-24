import { useEffect, useState } from 'react'
import { Ic } from '../../components/Ic'
import { getRagAssets } from '../../api/client'

/** 파일 행 */
function FileRow({ name, meta }) {
  return (
    <div className="flex items-center gap-2.5 px-3 py-2 rounded-lg hover:bg-zinc-50 dark:hover:bg-zinc-800/60">
      <Ic name="fileText" className="w-3.5 h-3.5 text-zinc-400 shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="text-[13px] text-zinc-700 dark:text-zinc-200 truncate">{name}</div>
        <div className="text-[11px] text-zinc-400">{meta}</div>
      </div>
      <span className="shrink-0 text-[10px] px-1.5 py-0.5 rounded-full bg-emerald-50 text-emerald-600 dark:bg-emerald-500/15 dark:text-emerald-300">
        학습완료
      </span>
      <button className="shrink-0 w-6 h-6 grid place-items-center rounded-md text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-700">
        <Ic name="x" className="w-3.5 h-3.5" />
      </button>
    </div>
  )
}

/** 에셋 그룹 카드 (어투 / 양식) */
function AssetGroup({ kind, name, active, files, onAddFile }) {
  const isTone = kind === 'tone'
  const badgeColor = isTone
    ? 'bg-blue-50 text-blue-600 dark:bg-blue-500/15 dark:text-blue-300'
    : 'bg-violet-50 text-violet-600 dark:bg-violet-500/15 dark:text-violet-300'
  const borderColor = active
    ? 'border-blue-300 dark:border-blue-500/40 ring-1 ring-blue-100 dark:ring-blue-500/20'
    : 'border-zinc-200 dark:border-zinc-800'

  return (
    <div className={`rounded-xl border bg-white dark:bg-zinc-900 overflow-hidden ${borderColor}`}>
      {/* 헤더 */}
      <div className="flex items-center gap-2.5 px-3.5 py-3 border-b border-zinc-100 dark:border-zinc-800">
        <div className={`w-8 h-8 rounded-lg grid place-items-center shrink-0 ${badgeColor}`}>
          <Ic name={isTone ? 'sparkles' : 'fileText'} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="text-sm font-semibold text-zinc-800 dark:text-zinc-100 truncate">{name}</span>
            {active && (
              <span className="shrink-0 text-[10px] px-1.5 py-0.5 rounded-full bg-blue-50 text-blue-600 dark:bg-blue-500/15 dark:text-blue-300">
                워크스페이스 적용중
              </span>
            )}
          </div>
          <div className="text-[11px] text-zinc-400">참조 파일 {files.length}개</div>
        </div>
        <button className="shrink-0 w-7 h-7 grid place-items-center rounded-lg text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800">
          <Ic name="dots" />
        </button>
      </div>

      {/* 파일 목록 */}
      <div className="p-1.5">
        {files.map((f, i) => <FileRow key={i} name={f.name} meta={f.meta} />)}
      </div>

      {/* 파일 추가 버튼 */}
      <button
        onClick={onAddFile}
        className="w-full flex items-center gap-1.5 px-3.5 py-2.5 border-t border-zinc-100 dark:border-zinc-800 text-xs text-blue-600 dark:text-blue-400 hover:bg-blue-50/50 dark:hover:bg-blue-500/10"
      >
        <Ic name="plus" className="w-3.5 h-3.5" />
        참조 파일 추가
      </button>
    </div>
  )
}

/** 섹션 헤더 + 그리드 */
function Section({ title, sub, addLabel, children }) {
  return (
    <div>
      <div className="flex items-end justify-between mb-3">
        <div>
          <h3 className="text-sm font-bold text-zinc-800 dark:text-zinc-100">{title}</h3>
          <p className="text-xs text-zinc-400 mt-0.5">{sub}</p>
        </div>
        <button className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 hover:bg-zinc-50 dark:hover:bg-zinc-700 text-xs px-2.5 py-1.5 text-zinc-600 dark:text-zinc-300">
          <Ic name="plus" className="w-3.5 h-3.5" />
          {addLabel}
        </button>
      </div>
      <div className="grid grid-cols-2 gap-4 items-start">{children}</div>
    </div>
  )
}

/**
 * 스타일 & 템플릿 (RAG) 뷰 (대시보드 메인 콘텐츠).
 */
export function StyleView() {
  const [assets, setAssets] = useState({ tones: [], forms: [] })

  useEffect(() => { getRagAssets().then(setAssets) }, [])

  return (
    <div className="flex flex-col gap-6">
      {/* 파일 업로드 드롭존 */}
      <div className="rounded-xl border-2 border-dashed border-zinc-300 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900/40 p-8 text-center">
        <div className="w-12 h-12 rounded-xl bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 grid place-items-center mx-auto mb-3 text-blue-600 dark:text-blue-400">
          <Ic name="upload" className="w-5 h-5" />
        </div>
        <div className="text-sm font-medium text-zinc-700 dark:text-zinc-200">
          어투 파일 · 표준 서식을 끌어다 놓으세요
        </div>
        <div className="text-xs text-zinc-400 mt-1">.docx · .hwp · .pdf 지원 — RAG 학습에 사용됩니다</div>
        <button className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium px-3.5 py-1.5">
          <Ic name="upload" className="w-3.5 h-3.5" />
          파일 선택
        </button>
      </div>

      {/* 어투 스타일 섹션 */}
      <Section
        title="어투 스타일"
        sub="하나의 어투에 여러 참조 파일을 연결해 문체를 학습시킵니다"
        addLabel="어투 추가"
      >
        {assets.tones.map(t => (
          <AssetGroup key={t.id} kind="tone" name={t.name} active={t.active} files={t.files} onAddFile={() => {}} />
        ))}
      </Section>

      {/* 서식 양식 섹션 */}
      <Section
        title="서식 양식"
        sub="하나의 양식에 여러 표준 템플릿 파일을 연결합니다"
        addLabel="양식 추가"
      >
        {assets.forms.map(f => (
          <AssetGroup key={f.id} kind="form" name={f.name} active={f.active} files={f.files} onAddFile={() => {}} />
        ))}
      </Section>
    </div>
  )
}
