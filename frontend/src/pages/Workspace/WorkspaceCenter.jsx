import { useState, useCallback, useMemo, useEffect, useLayoutEffect, useRef } from 'react'
import { Ic } from '../../components/Ic'
import { resolveViewer }            from '../../components/DocumentPanel'
import { ViewerShell }              from '../../components/ViewerShell'
import { useChangeSuggestions }     from '../../hooks/useChangeSuggestions'
import { usePatchTrigger }          from '../../hooks/usePatchTrigger'
import { useDocumentVersions }      from '../../hooks/useDocumentVersions'
import { fetchVersionFileBlob }     from '../../api/documentChanges'
import { AutomationBanner }         from './AutomationBanner'
import { ChangeSuggestionPanel }    from './ChangeSuggestionPanel'
import { VersionTabs }              from './VersionTabs'

function sameId(a, b) {
  return a != null && b != null && String(a) === String(b)
}

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
  suggestedWorkflow,
  // 채팅 patch_plan 메시지로부터 받은 patch 데이터 (부모 관리)
  localPatchData,
  // 채팅 [전체 반영] 버튼이 handleAcceptAll을 호출할 수 있도록 부모에 함수를 등록
  onAcceptAllReady,
}) {
  // 로컬 patch_changes가 있으면 snippetData에 합성, 없으면 원본 그대로
  // base가 null(HWP 등 corrections 없는 파일)이어도 localPatchData는 반영해야 한다
  const effectiveSnippetData = useMemo(() => {
    const base = previewData?.snippetData ?? null
    if (!localPatchData) return base
    return { ...(base ?? {}), patch_changes: localPatchData.patch_changes, version_id: localPatchData.version_id }
  }, [previewData?.snippetData, localPatchData])

  // uploadId: previewData.id (upload_log.id)
  // versionId: localPatchData.version_id 우선, 없으면 snippetData.version_id — BE 제공 시 활성화
  const uploadId  = previewData?.id                                                         ?? null
  const versionId = localPatchData?.version_id ?? previewData?.snippetData?.version_id     ?? null

  const {
    suggestions,
    statuses,
    setStatuses,
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

  const { patchStatus: rawPatchStatus, trigger } = usePatchTrigger(uploadId, versionId)

  // 버전 탭 — rawPatchStatus가 'generating'일 때 polling 시작.
  // versionId(채팅발 새 draft)가 바뀌면 즉시 재조회해 탭에 반영한다 (Fix B)
  const { versions } = useDocumentVersions(uploadId, rawPatchStatus, versionId)
  const autoPatchTriggeredVersionRef = useRef(null)

  const triggerDraftPatch = useCallback(async () => {
    if (!versionId) return
    if (sameId(autoPatchTriggeredVersionRef.current, versionId)) return
    autoPatchTriggeredVersionRef.current = versionId
    await trigger()
  }, [versionId, trigger])

  // accept-all 후 자동으로 patcher를 실행해 수정본 생성까지 한 번에 처리한다.
  // 버전이 이미 ready/failed이면 trigger를 호출하지 않아 불필요한 스피너를 방지한다.
  const handleAcceptAllAndPatch = useCallback(async (changeIds = null) => {
    await handleAcceptAll(changeIds)
    const currentVersion = versions.find(v => sameId(v.id, versionId))
    const needsPatch = versionId && (!currentVersion || currentVersion.status === 'draft')
    if (needsPatch) await triggerDraftPatch()
  }, [handleAcceptAll, versionId, versions, triggerDraftPatch])

  // 채팅 [전체 반영] 버튼이 accept-all+patch 함수를 호출할 수 있도록 부모에 등록
  useLayoutEffect(() => {
    onAcceptAllReady?.(handleAcceptAllAndPatch)
  }, [onAcceptAllReady, handleAcceptAllAndPatch])

  // versions polling 결과로 현재 versionId의 실제 상태를 반영한다.
  // rawPatchStatus가 null(초기값)이어도 versions에 ready/failed 버전이 있으면
  // 실제 상태를 반환해 autoSelectedRef 동기화와 뷰어 자동 전환이 동작하도록 한다.
  const patchStatus = useMemo(() => {
    if (versionId && versions.length > 0) {
      const current = versions.find(v => sameId(v.id, versionId))
      if (current && current.status !== 'draft' && current.status !== 'original') {
        // usePatchTrigger 타임아웃이 rawPatchStatus를 'failed'로 전환한 경우,
        // versions가 아직 'generating'이어도 'failed'를 우선 반영한다
        if (current.status === 'generating' && rawPatchStatus === 'failed') return 'failed'
        return current.status
      }
    }
    return rawPatchStatus
  }, [rawPatchStatus, versions, versionId])

  // 선택된 버전 ID (기본값: 원본 버전 ID 또는 null)
  const [selectedVersionId, setSelectedVersionId] = useState(null)
  const [versionBlobUrl, setVersionBlobUrl] = useState(null)
  const lastEditingVersionIdRef = useRef(null)

  useEffect(() => {
    autoPatchTriggeredVersionRef.current = null
  }, [versionId])

  const pendingSuggestionCount = useMemo(
    () => suggestions.filter(s => (statuses[s.id] ?? s.status ?? 'pending') === 'pending').length,
    [suggestions, statuses],
  )
  const appliedSuggestionCount = useMemo(
    () => suggestions.filter(s => (statuses[s.id] ?? s.status ?? 'pending') === 'applied').length,
    [suggestions, statuses],
  )

  // 방어적 자동 생성: 채팅/패널 어느 경로든 "적용됨 + 초안"이 남으면 수정본 생성을 시작한다.
  useEffect(() => {
    if (!uploadId || !versionId) return
    if (rawPatchStatus === 'generating') return
    if (suggestions.length === 0 || appliedSuggestionCount === 0 || pendingSuggestionCount > 0) return

    const currentVersion = versions.find(v => sameId(v.id, versionId))
    if (!currentVersion || currentVersion.status !== 'draft') return

    triggerDraftPatch()
  }, [
    uploadId,
    versionId,
    rawPatchStatus,
    suggestions.length,
    appliedSuggestionCount,
    pendingSuggestionCount,
    versions,
    triggerDraftPatch,
  ])

  useEffect(() => {
    lastEditingVersionIdRef.current = null
    setSelectedVersionId(null)
    setVersionBlobUrl(prev => {
      if (prev) URL.revokeObjectURL(prev)
      return null
    })
  }, [uploadId])

  // versions 목록이 처음 로드될 때 현재 편집 버전이 있으면 우선 선택하고, 없으면 원본을 선택
  useEffect(() => {
    if (versions.length === 0) return
    if (selectedVersionId !== null) return
    const editingVersion = versionId ? versions.find(v => sameId(v.id, versionId)) : null
    const original = versions.find(v => v.status === 'original')
    setSelectedVersionId((editingVersion ?? original ?? versions[0]).id)
  }, [versions, selectedVersionId, versionId])

  useEffect(() => {
    if (!versionId || versions.length === 0) return
    if (String(lastEditingVersionIdRef.current) === String(versionId)) return
    const editingVersion = versions.find(v => String(v.id) === String(versionId))
    if (!editingVersion) return
    lastEditingVersionIdRef.current = versionId
    setSelectedVersionId(editingVersion.id)
  }, [versionId, versions])

  // 버전 선택 시 Blob URL 관리 — 원본이 아닌 수정본 선택 시 파일을 내려받는다
  const handleSelectVersion = useCallback(async (version) => {
    setSelectedVersionId(version.id)

    if (version.status !== 'ready') {
      // 원본·초안·생성 실패 버전은 별도 artifact가 없으므로 원본 fileUrl로 복귀
      if (versionBlobUrl) URL.revokeObjectURL(versionBlobUrl)
      setVersionBlobUrl(null)
      return
    }

    // 완료된 수정본 — on-demand 다운로드 후 Blob URL 생성
    try {
      if (versionBlobUrl) URL.revokeObjectURL(versionBlobUrl)
      const blobUrl = await fetchVersionFileBlob(uploadId, version.id)
      setVersionBlobUrl(blobUrl)
    } catch {
      // 다운로드 실패 시 기존 URL 유지 (빈 값보다 낫다)
    }
  }, [uploadId, versionBlobUrl])

  // 패치 완료(ready) 시 수정본 버전을 자동 선택하고 제안 상태를 applied로 동기화한다.
  // snippet_data의 초기 status는 항상 'pending' 스냅샷이므로, version이 ready가 되면
  // 모든 pending 제안을 applied로 덮어써야 실제 DB 상태와 일치한다.
  const autoSelectedRef = useRef(false)

  // versionId가 바뀌면 자동 선택 플래그를 초기화해 새 버전도 자동 선택되도록 한다
  useEffect(() => {
    autoSelectedRef.current = false
  }, [versionId])

  useEffect(() => {
    if (patchStatus !== 'ready' || !versionId) return
    const readyVersion = versions.find(v => sameId(v.id, versionId) && v.status === 'ready')
    if (!readyVersion) return
    if (!autoSelectedRef.current) {
      autoSelectedRef.current = true
      handleSelectVersion(readyVersion)
    }
    // DB 상태 동기화: ready 버전의 applied_change_ids가 있으면 그 기준으로, 없으면 전체 applied
    const appliedIds = new Set(readyVersion.applied_change_ids ?? [])
    setStatuses(prev => {
      const next = { ...prev }
      for (const s of suggestions) {
        if (!s.changeDbId) continue
        if (appliedIds.size === 0 || appliedIds.has(s.changeDbId)) {
          next[s.id] = 'applied'
        }
      }
      return next
    })
  }, [patchStatus, versionId, versions, handleSelectVersion, suggestions, setStatuses])

  // 뷰어에 전달할 fileUrl — 수정본 선택 시 Blob URL, 원본 선택 시 previewData.fileUrl
  const selectedVersion = useMemo(() => {
    if (!selectedVersionId || versions.length === 0) return null
    return versions.find(v => sameId(v.id, selectedVersionId)) ?? null
  }, [selectedVersionId, versions])

  const selectedUsesOriginalFile = useMemo(() => {
    if (!selectedVersionId || versions.length === 0) return true
    return !selectedVersion || selectedVersion.status !== 'ready'
  }, [selectedVersionId, versions, selectedVersion])

  const selectedShowsCurrentChanges = useMemo(() => {
    if (!versionId || !selectedVersionId) return suggestions.length > 0
    return sameId(selectedVersionId, versionId)
  }, [selectedVersionId, versionId, suggestions.length])

  const visibleSuggestions = selectedShowsCurrentChanges ? suggestions : []
  const visibleHighlights = selectedShowsCurrentChanges ? highlights : []

  // 최종본 다운로드 (Fix A) — 선택된 버전 기준으로 실제 파일을 내려받는다.
  // 수정본: 버전 파일 API의 Blob을 a[download]로 저장. 원본: 원본 fileUrl 저장.
  const handleDownload = useCallback(async () => {
    const selected = versions.find(v => sameId(v.id, selectedVersionId))
    const filename = previewData?.filename ?? 'document'

    const saveAs = (href, name) => {
      const a = document.createElement('a')
      a.href = href
      a.download = name
      document.body.appendChild(a)
      a.click()
      a.remove()
    }

    if (!selected || selected.status !== 'ready') {
      if (previewData?.fileUrl) saveAs(previewData.fileUrl, filename)
      return
    }
    try {
      const blobUrl = await fetchVersionFileBlob(uploadId, selected.id)
      const dot = filename.lastIndexOf('.')
      const versioned = dot > 0
        ? `${filename.slice(0, dot)}_v${selected.version_number}${filename.slice(dot)}`
        : `${filename}_v${selected.version_number}`
      saveAs(blobUrl, versioned)
      // 즉시 revoke하면 브라우저가 Blob을 읽기 전에 무효화될 수 있어 지연 해제한다
      setTimeout(() => URL.revokeObjectURL(blobUrl), 10_000)
    } catch {
      // 다운로드 실패 — 뷰어 상태는 건드리지 않는다 (재시도 가능)
    }
  }, [versions, selectedVersionId, previewData, uploadId])

  // 수정본 선택 시 fileUrl을 Blob URL로 교체한 previewData를 뷰어에 전달
  // previewData가 null인 동안에도 훅은 항상 호출돼야 하므로 early return보다 위에 둔다
  const effectivePreviewData = useMemo(() => {
    if (!previewData) return previewData
    if (selectedUsesOriginalFile || !versionBlobUrl) return previewData
    return { ...previewData, fileUrl: versionBlobUrl }
  }, [previewData, selectedUsesOriginalFile, versionBlobUrl])

  // 파일 미선택 상태 — 모든 hook 호출 이후에 early return
  if (!previewData) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center bg-zinc-100 dark:bg-zinc-950 text-zinc-400">
        <Ic name="fileText" className="w-10 h-10 mb-3 opacity-20" />
        <p className="text-sm">좌측에서 파일을 선택하면 문서가 표시됩니다</p>
      </div>
    )
  }

  const { filename, artifactUrl } = previewData

  return (
    <ViewerShell
      className="flex-1 min-w-0 flex flex-col relative bg-zinc-50 dark:bg-zinc-950 border-r border-zinc-200 dark:border-zinc-800"
      filename={filename}
      artifactUrl={artifactUrl}
      onDownload={handleDownload}
      onClose={onCloseViewer}
      onNewWindow={() => {
        // localStorage에 previewData 저장 후 /preview 탭 열기
        localStorage.setItem('ax_preview_data', JSON.stringify(previewData))
        window.open('/preview', '_blank')
      }}
      versionPanel={
        <VersionTabs
          versions={versions}
          selectedVersionId={selectedVersionId}
          onSelectVersion={handleSelectVersion}
        />
      }
      sidePanel={
        visibleSuggestions.length > 0 ? (
          <ChangeSuggestionPanel
            suggestions={visibleSuggestions}
            statuses={statuses}
            pendingIds={pendingIds}
            onSetStatus={handleSetStatus}
            onAcceptAll={handleAcceptAllAndPatch}
            isAcceptingAll={isAcceptingAll}
            acceptAllError={acceptAllError}
            autoRejectedIds={autoRejectedIds}
            selectedSuggestionId={selectedSuggestionId}
            onSelectSuggestion={setSelectedSuggestionId}
            uploadId={uploadId}
            versionId={versionId}
            patchStatus={patchStatus}
            onPatch={selectedShowsCurrentChanges && versionId ? trigger : null}
          />
        ) : null
      }
      inputPanel={null}
      banner={showBanner ? <AutomationBanner workflow={suggestedWorkflow} onDismiss={onDismissBanner} /> : null}
    >
      {resolveViewer(effectivePreviewData, {
        highlights:            visibleHighlights,
        selectedHighlightId:  selectedSuggestionId,
        onSelectHighlight:    handleSelectHighlight,
      })}
    </ViewerShell>
  )
}
