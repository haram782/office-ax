import { useState, useCallback, useMemo, useEffect } from 'react'
import { Ic } from '../../components/Ic'
import { resolveViewer }            from '../../components/DocumentPanel'
import { ViewerShell }              from '../../components/ViewerShell'
import { useChangeSuggestions }     from '../../hooks/useChangeSuggestions'
import { usePatchTrigger }          from '../../hooks/usePatchTrigger'
import { useGeneratePatchPlan }     from '../../hooks/useGeneratePatchPlan'
import { useDocumentVersions }      from '../../hooks/useDocumentVersions'
import { fetchVersionFileBlob }     from '../../api/documentChanges'
import { AutomationBanner }         from './AutomationBanner'
import { ChangeSuggestionPanel }    from './ChangeSuggestionPanel'
import { PatchRequestInput }        from './PatchRequestInput'
import { VersionTabs }              from './VersionTabs'

/**
 * 워크스페이스 중앙 문서 뷰어 영역.
 * 파일이 선택된 경우 ViewerShell + resolveViewer()로 뷰어를 렌더한다.
 * 선택된 파일이 없으면 안내 메시지를 보여준다.
 */
export function WorkspaceCenter({
  previewData,
  onCloseViewer,
  showBanner,
  onDismissBanner,
}) {
  // generatePatchPlan 성공 시 받은 patch_changes + version_id를 로컬에 보관
  // previewData.snippetData에 overlay해서 useChangeSuggestions에 전달한다
  const [localPatchData, setLocalPatchData] = useState(null)

  // onSuccess: version_id + changes를 로컬 상태에 저장
  const handlePatchPlanSuccess = useCallback((data) => {
    setLocalPatchData({ version_id: data.version_id, patch_changes: data.changes ?? [] })
  }, [])

  // 로컬 patch_changes가 있으면 snippetData에 합성, 없으면 원본 그대로
  const effectiveSnippetData = useMemo(() => {
    const base = previewData?.snippetData ?? null
    if (!localPatchData || !base) return base
    return { ...base, patch_changes: localPatchData.patch_changes, version_id: localPatchData.version_id }
  }, [previewData?.snippetData, localPatchData])

  // uploadId: previewData.id (upload_log.id)
  // versionId: localPatchData.version_id 우선, 없으면 snippetData.version_id — BE 제공 시 활성화
  const uploadId  = previewData?.id                                                         ?? null
  const versionId = localPatchData?.version_id ?? previewData?.snippetData?.version_id     ?? null

  const {
    suggestions,
    statuses,
    selectedSuggestionId,
    setSelectedSuggestionId,
    highlights,
    pendingIds,
    isAcceptingAll,
    acceptAllError,
    autoRejectedIds,
    handleSetStatus,
    handleAcceptAll,
    handleSelectHighlight,
  } = useChangeSuggestions(effectiveSnippetData, uploadId, versionId)

  const { patchStatus, trigger } = usePatchTrigger(uploadId, versionId)

  const { generate, isGenerating, error: generateError } = useGeneratePatchPlan(uploadId, handlePatchPlanSuccess)

  // 버전 탭 — patchStatus가 'ready'가 되면 재조회
  const { versions } = useDocumentVersions(uploadId, patchStatus)

  // 선택된 버전 ID (기본값: 원본 버전 ID 또는 null)
  const [selectedVersionId, setSelectedVersionId] = useState(null)

  // versions 목록이 처음 로드될 때 원본 버전을 기본 선택
  useEffect(() => {
    if (versions.length === 0) return
    if (selectedVersionId !== null) return
    const original = versions.find(v => v.status === 'original')
    if (original) setSelectedVersionId(original.id)
  }, [versions, selectedVersionId])

  // 버전 선택 시 Blob URL 관리 — 원본이 아닌 수정본 선택 시 파일을 내려받는다
  const [versionBlobUrl, setVersionBlobUrl] = useState(null)

  const handleSelectVersion = useCallback(async (version) => {
    setSelectedVersionId(version.id)

    if (version.status === 'original') {
      // 원본 — 이전 Blob URL 해제 후 원본 fileUrl로 복귀
      if (versionBlobUrl) URL.revokeObjectURL(versionBlobUrl)
      setVersionBlobUrl(null)
      return
    }

    // 수정본 — on-demand 다운로드 후 Blob URL 생성
    try {
      if (versionBlobUrl) URL.revokeObjectURL(versionBlobUrl)
      const blobUrl = await fetchVersionFileBlob(uploadId, version.id)
      setVersionBlobUrl(blobUrl)
    } catch {
      // 다운로드 실패 시 기존 URL 유지 (빈 값보다 낫다)
    }
  }, [uploadId, versionBlobUrl])

  // 뷰어에 전달할 fileUrl — 수정본 선택 시 Blob URL, 원본 선택 시 previewData.fileUrl
  const selectedIsOriginal = useMemo(() => {
    if (!selectedVersionId || versions.length === 0) return true
    const v = versions.find(v => v.id === selectedVersionId)
    return !v || v.status === 'original'
  }, [selectedVersionId, versions])

  // 파일 미선택 상태 — hook 호출 이후에 early return
  if (!previewData) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center bg-zinc-100 dark:bg-zinc-950 text-zinc-400">
        <Ic name="fileText" className="w-10 h-10 mb-3 opacity-20" />
        <p className="text-sm">좌측에서 파일을 선택하면 문서가 표시됩니다</p>
      </div>
    )
  }

  const { filename, artifactUrl } = previewData

  // 수정본 선택 시 fileUrl을 Blob URL로 교체한 previewData를 뷰어에 전달
  const effectivePreviewData = useMemo(() => {
    if (selectedIsOriginal || !versionBlobUrl) return previewData
    return { ...previewData, fileUrl: versionBlobUrl }
  }, [previewData, selectedIsOriginal, versionBlobUrl])

  return (
    <ViewerShell
      className="flex-1 min-w-0 flex flex-col relative bg-zinc-50 dark:bg-zinc-950 border-r border-zinc-200 dark:border-zinc-800"
      filename={filename}
      artifactUrl={artifactUrl}
      onClose={onCloseViewer}
      onNewWindow={() => {
        // localStorage에 previewData 저장 후 /preview 탭 열기
        localStorage.setItem('ax_preview_data', JSON.stringify(previewData))
        window.open('/preview', '_blank')
      }}
      headerExtra={
        <VersionTabs
          versions={versions}
          selectedVersionId={selectedVersionId}
          onSelectVersion={handleSelectVersion}
        />
      }
      sidePanel={
        suggestions.length > 0 ? (
          <ChangeSuggestionPanel
            suggestions={suggestions}
            statuses={statuses}
            pendingIds={pendingIds}
            onSetStatus={handleSetStatus}
            onAcceptAll={handleAcceptAll}
            isAcceptingAll={isAcceptingAll}
            acceptAllError={acceptAllError}
            autoRejectedIds={autoRejectedIds}
            selectedSuggestionId={selectedSuggestionId}
            onSelectSuggestion={setSelectedSuggestionId}
            uploadId={uploadId}
            versionId={versionId}
            patchStatus={patchStatus}
            onPatch={versionId ? trigger : null}
          />
        ) : null
      }
      inputPanel={
        <PatchRequestInput
          uploadId={uploadId}
          onGenerate={generate}
          isGenerating={isGenerating}
          error={generateError}
        />
      }
      banner={showBanner ? <AutomationBanner onDismiss={onDismissBanner} /> : null}
    >
      {resolveViewer(effectivePreviewData, {
        highlights,
        selectedHighlightId:  selectedSuggestionId,
        onSelectHighlight:    handleSelectHighlight,
      })}
    </ViewerShell>
  )
}
