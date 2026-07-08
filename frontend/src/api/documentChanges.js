/**
 * DocumentChange REST API — PATCH /api/v1/documents/changes/{id}/
 *
 * client.js의 axios 인스턴스를 재사용해 인증 인터셉터(Token 헤더)를 공유한다.
 */
import { api } from './client'

/**
 * DocumentChange 상태를 변경한다.
 *
 * @param {number|string} changeDbId - DocumentChange DB PK
 * @param {'applied'|'rejected'|'pending'} status
 * @returns {Promise<object>} 수정된 DocumentChange 전체
 */
export async function patchDocumentChange(changeDbId, status) {
  const { data } = await api.patch(`/changes/${changeDbId}/`, { status })
  return data
}

/**
 * XLSX patcher를 트리거한다.
 * applied 상태의 변경을 반영한 수정본 생성을 BE에 요청한다.
 *
 * @param {number|string} uploadId   - 업로드 ID
 * @param {number|string} versionId  - 버전 ID
 * @returns {Promise<{ version_id: number, status: string }>}
 */
export async function triggerPatch(uploadId, versionId) {
  const { data } = await api.post(
    `/uploads/${uploadId}/versions/${versionId}/patch/`,
  )
  return data
}

/**
 * AI 기반 패치 플랜을 생성한다.
 * 사용자 프롬프트를 받아 변경 제안 목록을 생성한다.
 *
 * @param {number|string} uploadId - 업로드 ID
 * @param {string}        prompt   - 사용자 수정 요청 텍스트
 * @returns {Promise<{ version_id: number, changes: Array }>}
 */
export async function generatePatchPlan(uploadId, prompt) {
  const { data } = await api.post(
    `/uploads/${uploadId}/generate-patch-plan/`,
    { prompt },
  )
  return data
}

/**
 * pending 상태 변경 전체를 적용한다.
 * 같은 위치(anchor) 충돌은 서버가 confidence 기준으로 자동 해소한다
 * (가장 높은 confidence만 applied, 나머지는 rejected로 자동 반려).
 *
 * @param {number|string} uploadId
 * @param {number|string} versionId
 * @param {number[]|null} changeIds - 지정 시 해당 change만 부분 반영 (체크박스 선택)
 * @returns {Promise<{ applied: Array, rejected: Array }>}
 */
export async function acceptAllChanges(uploadId, versionId, changeIds = null) {
  const { data } = await api.post(
    `/uploads/${uploadId}/versions/${versionId}/changes/accept-all/`,
    changeIds ? { change_ids: changeIds } : {},
  )
  return data
}

/**
 * 업로드에 속한 DocumentVersion 목록을 조회한다.
 *
 * @param {number|string} uploadId
 * @returns {Promise<Array<{ id, version_number, status, label, summary, applied_change_ids, created_at, updated_at }>>}
 */
export async function fetchDocumentVersions(uploadId) {
  const { data } = await api.get(`/uploads/${uploadId}/versions/`)
  return data
}

/**
 * 수정본 파일을 on-demand로 내려받아 Blob URL을 반환한다.
 * 뷰어 표시용 — 원본(original) 버전에는 사용하지 않는다.
 *
 * @param {number|string} uploadId
 * @param {number|string} versionId
 * @returns {Promise<string>} Blob URL (blob:...)
 */
export async function fetchVersionFileBlob(uploadId, versionId) {
  const response = await api.get(
    `/uploads/${uploadId}/versions/${versionId}/file/`,
    { responseType: 'blob' },
  )
  return URL.createObjectURL(response.data)
}
