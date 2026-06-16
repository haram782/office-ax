import axios from 'axios'

const api = axios.create({ baseURL: '/api/v1' })

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('auth_token')
  if (token) config.headers.Authorization = `Token ${token}`
  return config
})

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

export async function createChatSession(title = '') {
  const { data } = await api.post('/chat/sessions/', { title })
  return data  // { id, title, created_at }
}

export async function getChatMessages(sessionId) {
  const { data } = await api.get(`/chat/sessions/${sessionId}/messages/`)
  return data  // ChatMessage[]
}

export async function sendChatMessage(sessionId, content, file = null) {
  const form = new FormData()
  form.append('content', content)
  if (file) form.append('file', file)
  const { data } = await api.post(
    `/chat/sessions/${sessionId}/messages/send/`,
    form,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  )
  return data  // { message_id, session_id, status }
}
