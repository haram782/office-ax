import axios from 'axios'

const api = axios.create({ baseURL: '/api/v1' })
// documentChanges.js 등 하위 모듈에서 인증 인터셉터를 공유하기 위해 export
export { api }

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('auth_token')
  if (token) config.headers.Authorization = `Token ${token}`
  return config
})

// 크레딧 소진(429) 전역 처리 — 어느 API에서 오든 한 곳에서 안내 모달을 띄운다.
// reject는 그대로 유지해 각 훅의 개별 에러 처리(스피너 해제 등)를 깨지 않는다.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 429) {
      const message =
        error.response.data?.error || '이번 달 사용량을 모두 썼어요. 다음 달에 초기화됩니다.'
      window.dispatchEvent(new CustomEvent('ax:credit-exhausted', { detail: message }))
    }
    return Promise.reject(error)
  }
)

// ── 인증 API ──────────────────────────────────────────────────────────────────

/** Google OAuth 액세스 토큰으로 서버 인증 → { token, user } 반환 */
export async function googleLogin(accessToken) {
  const { data } = await api.post('/auth/google/', { access_token: accessToken })
  return data
}

/** 현재 로그인 사용자 정보 조회 */
export async function getMe() {
  const { data } = await api.get('/auth/me/')
  return data
}

// ── 기존 문서 업로드 API (레거시 단방향 플로우) ────────────────────────────────

export async function uploadFile(file) {
  const form = new FormData()
  form.append('file', file)
  const { data } = await api.post('/uploads/', form)
  return data
}

export async function getUploadResult(uploadId) {
  const { data } = await api.get(`/uploads/${uploadId}/`)
  return data
}

export async function getSuggestedWorkflows() {
  const { data } = await api.get('/workflows/')
  return data
}

export async function activateWorkflow(workflowId, phoneNumber) {
  const { data } = await api.post(`/workflows/${workflowId}/activate/`, {
    channel: 'kakao',
    phone_number: phoneNumber,
  })
  return data
}

// ── 채팅 워크스페이스 API ────────────────────────────────────────────────────

/** 저장된 전체 채팅 세션 목록 조회 */
export async function getChatSessions() {
  const { data } = await api.get('/chat/sessions/')
  return data  // [{ id, title, message_count, messages, created_at, updated_at }]
}

export async function createChatSession(title = '') {
  const { data } = await api.post('/chat/sessions/', { title })
  return data  // { id, title, created_at }
}

export async function getChatMessages(sessionId) {
  const { data } = await api.get(`/chat/sessions/${sessionId}/messages/`)
  return data  // ChatMessage[]
}

export async function sendChatMessage(sessionId, content, file = null, uploadId = null, ragAssetIds = null) {
  const form = new FormData()
  form.append('content', content)
  if (file) form.append('file', file)
  // BE가 채팅 맥락에서 참조할 문서 upload_id (patch_plan 생성 등에 사용)
  if (uploadId != null) form.append('upload_id', String(uploadId))
  // 선택된 RAG 자산 — BE가 소유 검증 후 text_chat에 파일 경로로 전달
  if (ragAssetIds?.length) form.append('rag_asset_ids', JSON.stringify(ragAssetIds))
  const { data } = await api.post(
    `/chat/sessions/${sessionId}/messages/send/`,
    form,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  )
  return data  // { message_id, session_id, status }
}

// ── Dashboard ─────────────────────────────────────────────────────────────

/** 이번 달 UsageEvent 기반 대시보드 통계 조회 */
export async function getDashboardStats() {
  const { data } = await api.get('/dashboard/stats/')
  return data
}

// ── Pipeline / Email / RAG — BE 미완성 구간 더미 데이터 ─────────────────────
// BE 완성 후 아래 함수들을 실제 api 호출로 교체한다.

// ── Pipeline CRUD ────────────────────────────────────────────────────────────

/** 파이프라인 목록 조회 */
export async function getPipelines() {
  const { data } = await api.get('/pipelines/')
  return data
}

/** 파이프라인 단건 조회 */
export async function getPipelineById(id) {
  const { data } = await api.get(`/pipelines/${id}/`)
  return data
}

/** 파이프라인 생성 */
export async function createPipeline(payload) {
  const { data } = await api.post('/pipelines/', payload)
  return data
}

/** 파이프라인 수정 */
export async function updatePipeline(id, payload) {
  const { data } = await api.patch(`/pipelines/${id}/`, payload)
  return data
}

/** 파이프라인 삭제 */
export async function deletePipeline(id) {
  const { data } = await api.delete(`/pipelines/${id}/`)
  return data
}

// ── Step CRUD ────────────────────────────────────────────────────────────────

/** 파이프라인에 속한 스텝 목록 조회 */
export async function getPipelineSteps(pipelineId) {
  const { data } = await api.get(`/pipelines/${pipelineId}/steps/`)
  return data
}

/** 스텝 생성 */
export async function createStep(pipelineId, payload) {
  const { data } = await api.post(`/pipelines/${pipelineId}/steps/`, payload)
  return data
}

/** 스텝 수정 */
export async function updateStep(pipelineId, stepId, payload) {
  const { data } = await api.patch(`/pipelines/${pipelineId}/steps/${stepId}/`, payload)
  return data
}

/** 스텝 삭제 */
export async function deleteStep(pipelineId, stepId) {
  const { data } = await api.delete(`/pipelines/${pipelineId}/steps/${stepId}/`)
  return data
}

/** 스텝 순서 재정렬 — orders: [{ id, step_order }, ...] */
export async function reorderSteps(pipelineId, orders) {
  const { data } = await api.post(`/pipelines/${pipelineId}/steps/reorder/`, { orders })
  return data
}

/** 파이프라인 실행기록 조회 */
export async function getPipelineRuns(pipelineId) {
  const { data } = await api.get(`/pipelines/${pipelineId}/runs/`)
  return data
}

// InboundEmail status 값 → 사용자 표시 라벨
const EMAIL_STATUS_LABELS = {
  received: '수신',
  processing: '처리 중',
  done: '완료',
  failed: '실패',
}

/** 수신 시각을 짧은 표시 형태로 변환 (오늘이면 시각, 아니면 월-일) */
function formatEmailTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const sameDay = d.toDateString() === now.toDateString()
  return sameDay
    ? d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })
    : d.toLocaleDateString('ko-KR', { month: '2-digit', day: '2-digit' }).replace(/\. ?/g, '-').replace(/-$/, '')
}

/** 인바운드 이메일 수신함 조회 — InboundEmailSerializer 필드를 화면 형태로 매핑 */
export async function getEmailInbox() {
  const { data } = await api.get('/email-inbox/')
  return data.map((row) => ({
    id:      row.id,
    from:    row.sender,
    subject: row.subject,
    file:    row.attachment_filename,
    time:    formatEmailTime(row.received_at),
    status:  EMAIL_STATUS_LABELS[row.status] ?? row.status,
  }))
}

/** RAG 자산 목록 조회 — kind·group_name 기준으로 그룹핑해 반환 */
export async function getRagAssets() {
  const { data } = await api.get('/rag-assets/')

  const groupBy = (kind) => {
    const groups = new Map()
    for (const a of data.filter(x => x.kind === kind)) {
      if (!groups.has(a.group_name)) groups.set(a.group_name, { name: a.group_name, assetIds: [], files: [] })
      const g = groups.get(a.group_name)
      g.assetIds.push(a.id)
      g.files.push({ id: a.id, name: (a.file ?? '').split('/').pop(), meta: `${Math.round((a.file_size ?? 0) / 1024)} KB` })
    }
    return [...groups.values()]
  }

  return { tones: groupBy('tone'), forms: groupBy('form') }
}

/** RAG 자산 업로드 — 업로드 후 백엔드가 학습 태스크를 예약한다 */
export async function uploadRagAsset(kind, groupName, file) {
  const form = new FormData()
  form.append('kind', kind)
  form.append('group_name', groupName)
  form.append('file', file)
  const { data } = await api.post('/rag-assets/', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

/** RAG 자산 삭제 */
export async function deleteRagAsset(assetId) {
  await api.delete(`/rag-assets/${assetId}/`)
}

/** RAG 자산 파일의 다운로드 URL 조회 (뷰어 팝업에서 사용) */
export async function getRagAssetFileUrl(assetId) {
  const { data } = await api.get(`/rag-assets/${assetId}/file/`)
  return data.file_url
}
