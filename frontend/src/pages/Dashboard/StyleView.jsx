import { useCallback, useEffect, useRef, useState } from 'react'
import { Ic } from '../../components/Ic'
import { getRagAssets, uploadRagAsset, deleteRagAsset, getRagAssetFileUrl } from '../../api/client'
import { SubViewerPopup } from '../Workspace/SubViewerPopup'

/** 파일명에서 확장자를 뗀 것을 그룹명으로 사용한다 (Workspace RagSelector와 동일 규칙) */
function groupNameFromFile(file) {
  return file.name.replace(/\.[^.]+$/, '')
}

/**
 * 파일 행 — 클릭 시 SubViewerPopup 열기, x 버튼으로 삭제.
 */
function FileRow({ id, name, meta, onView, onDelete }) {
  return (
    <div className="flex items-center gap-2.5 px-3 py-2 rounded-lg hover:bg-zinc-50 dark:hover:bg-zinc-800/60">
      <button
        onClick={() => onView(id, name)}
        className="flex items-center gap-2 flex-1 min-w-0 text-left"
      >
        <Ic name="fileText" className="w-3.5 h-3.5 text-zinc-400 shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="text-[13px] text-blue-600 dark:text-blue-400 hover:underline truncate">{name}</div>
          <div className="text-[11px] text-zinc-400">{meta}</div>
        </div>
      </button>
      <span className="shrink-0 text-[10px] px-1.5 py-0.5 rounded-full bg-emerald-50 text-emerald-600 dark:bg-emerald-500/15 dark:text-emerald-300">
        학습완료
      </span>
      <button
        onClick={() => onDelete(id, name)}
        className="shrink-0 w-6 h-6 grid place-items-center rounded-md text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-700"
      >
        <Ic name="x" className="w-3.5 h-3.5" />
      </button>
    </div>
  )
}

/** 에셋 그룹 카드 (어투 / 양식) */
function AssetGroup({ kind, name, files, onAddFile, onViewFile, onDeleteFile }) {
  const isTone = kind === 'tone'
  const badgeColor = isTone
    ? 'bg-blue-50 text-blue-600 dark:bg-blue-500/15 dark:text-blue-300'
    : 'bg-violet-50 text-violet-600 dark:bg-violet-500/15 dark:text-violet-300'
  const fileInputRef = useRef(null)

  return (
    <div className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 overflow-hidden shadow-sm">
      {/* 헤더 */}
      <div className="flex items-center gap-2.5 px-3.5 py-3 border-b border-zinc-100 dark:border-zinc-800">
        <div className={`w-8 h-8 rounded-lg grid place-items-center shrink-0 ${badgeColor}`}>
          <Ic name={isTone ? 'sparkles' : 'fileText'} />
        </div>
        <div className="flex-1 min-w-0">
          <span className="text-sm font-semibold text-zinc-800 dark:text-zinc-100 truncate">{name}</span>
          <div className="text-[11px] text-zinc-400">참조 파일 {files.length}개</div>
        </div>
      </div>

      {/* 파일 목록 */}
      <div className="p-1.5">
        {files.map((f) => (
          <FileRow key={f.id} id={f.id} name={f.name} meta={f.meta} onView={onViewFile} onDelete={onDeleteFile} />
        ))}
      </div>

      {/* 파일 추가 버튼 — 같은 그룹(kind+name)에 파일을 추가한다 */}
      <button
        onClick={() => fileInputRef.current?.click()}
        className="w-full flex items-center gap-1.5 px-3.5 py-2.5 border-t border-zinc-100 dark:border-zinc-800 text-xs text-blue-600 dark:text-blue-400 hover:bg-blue-50/50 dark:hover:bg-blue-500/10"
      >
        <Ic name="plus" className="w-3.5 h-3.5" />
        참조 파일 추가
      </button>
      <input
        ref={fileInputRef}
        type="file"
        data-group={name}
        className="hidden"
        accept=".docx,.hwp,.pdf,.xlsx,.csv"
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) onAddFile(kind, name, file)
          e.target.value = ''
        }}
      />
    </div>
  )
}

/** 어투/서식 전용 드롭존 — 드래그앤드롭 또는 클릭으로 새 그룹을 만든다 */
function KindDropzone({ kind, label, hint, onDropFile }) {
  const inputRef = useRef(null)
  const [dragOver, setDragOver] = useState(false)

  const handleFiles = (files) => {
    const file = files?.[0]
    if (file) onDropFile(kind, groupNameFromFile(file), file)
  }

  return (
    <div
      data-testid={`${kind}-dropzone`}
      onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDragOver(false)
        handleFiles(e.dataTransfer?.files)
      }}
      className={`rounded-xl border-2 border-dashed p-5 text-center transition-colors ${
        dragOver
          ? 'border-blue-400 bg-blue-50/50 dark:bg-blue-500/10'
          : 'border-zinc-300 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900/40'
      }`}
    >
      <div className="w-9 h-9 rounded-lg bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 grid place-items-center mx-auto mb-2 text-blue-600 dark:text-blue-400">
        <Ic name="upload" className="w-4 h-4" />
      </div>
      <div className="text-xs font-medium text-zinc-700 dark:text-zinc-200">{label}</div>
      <div className="text-[11px] text-zinc-400 mt-0.5">{hint}</div>
      <button
        onClick={() => inputRef.current?.click()}
        className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium px-3 py-1.5"
      >
        <Ic name="upload" className="w-3.5 h-3.5" />
        파일 선택
      </button>
      <input
        ref={inputRef}
        type="file"
        className="hidden"
        accept=".docx,.hwp,.pdf,.xlsx,.csv"
        onChange={(e) => { handleFiles(e.target.files); e.target.value = '' }}
      />
    </div>
  )
}

/** 섹션 헤더 + 그리드 */
function Section({ title, sub, children }) {
  return (
    <div>
      <div className="mb-3">
        <h3 className="text-sm font-bold text-zinc-800 dark:text-zinc-100">{title}</h3>
        <p className="text-xs text-zinc-400 mt-0.5">{sub}</p>
      </div>
      <div className="grid grid-cols-2 gap-4 items-start">{children}</div>
    </div>
  )
}

/**
 * 스타일 & 템플릿 (RAG) 뷰 (대시보드 메인 콘텐츠).
 *
 * 어투/서식 전용 드롭존으로 새 그룹을 만들고, 그룹 카드의 [참조 파일 추가]로
 * 기존 그룹에 파일을 더한다. FileRow 클릭 → 파일 URL 조회 후 SubViewerPopup.
 * "워크스페이스 적용중" 배지는 실데이터에 없는 개념이라 제거했다.
 */
export function StyleView() {
  const [assets, setAssets] = useState({ tones: [], forms: [] })
  // { filename, fileUrl } | null
  const [popup, setPopup] = useState(null)

  const refresh = useCallback(() => {
    getRagAssets().then(setAssets)
  }, [])
  useEffect(() => { refresh() }, [refresh])

  const handleUpload = useCallback(async (kind, groupName, file) => {
    try {
      await uploadRagAsset(kind, groupName, file)
      refresh()
    } catch {
      // 업로드 실패 — 목록은 그대로 두고 재시도 가능하게 한다
    }
  }, [refresh])

  const handleDelete = useCallback(async (id, name) => {
    if (!window.confirm(`'${name}' 파일을 삭제할까요?`)) return
    try {
      await deleteRagAsset(id)
      refresh()
    } catch {
      // 삭제 실패 — 목록은 그대로 유지
    }
  }, [refresh])

  const handleViewFile = useCallback(async (id, filename) => {
    try {
      const fileUrl = await getRagAssetFileUrl(id)
      setPopup({ filename, fileUrl })
    } catch {
      setPopup({ filename, fileUrl: '' })
    }
  }, [])

  return (
    <>
      <div className="flex flex-col gap-6">
        {/* 어투 스타일 섹션 */}
        <Section title="어투 스타일" sub="하나의 어투에 여러 참조 파일을 연결해 문체를 학습시킵니다">
          <KindDropzone
            kind="tone"
            label="어투 파일을 끌어다 놓으세요"
            hint=".docx · .hwp · .pdf 지원 — 새 어투로 등록됩니다"
            onDropFile={handleUpload}
          />
          {assets.tones.map(t => (
            <AssetGroup
              key={t.name} kind="tone" name={t.name} files={t.files}
              onAddFile={handleUpload} onViewFile={handleViewFile} onDeleteFile={handleDelete}
            />
          ))}
        </Section>

        {/* 서식 양식 섹션 */}
        <Section title="서식 양식" sub="하나의 양식에 여러 표준 템플릿 파일을 연결합니다">
          <KindDropzone
            kind="form"
            label="표준 서식을 끌어다 놓으세요"
            hint=".docx · .hwp · .pdf 지원 — 새 양식으로 등록됩니다"
            onDropFile={handleUpload}
          />
          {assets.forms.map(f => (
            <AssetGroup
              key={f.name} kind="form" name={f.name} files={f.files}
              onAddFile={handleUpload} onViewFile={handleViewFile} onDeleteFile={handleDelete}
            />
          ))}
        </Section>
      </div>

      {/* RAG 문서 뷰어 팝업 */}
      {popup && (
        <SubViewerPopup
          filename={popup.filename}
          fileUrl={popup.fileUrl}
          title={`RAG 문서 · ${popup.filename}`}
          onClose={() => setPopup(null)}
        />
      )}
    </>
  )
}
