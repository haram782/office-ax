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

// ── Dashboard / Pipeline / Email / RAG — BE 미완성 구간 더미 데이터 ─────────────
// BE 완성 후 아래 함수들을 실제 api 호출로 교체한다.

export async function getDashboardStats() {
  return {
    tokens:    { used: 716000, total: 2000000, percent: 64, daysLeft: 18 },
    balance:   { remaining: 312000, total: 500000, used: 188000 },
    processed: { count: 1842, errors: 327, corrected: 1515, chart: [40, 65, 52, 78, 60, 88, 72] },
  }
}

export async function getPipelines() {
  return [
    { id: 1, name: '청약서 자동 검토 및 보정',  tags: ['C'],      meta: '매일 09:00 · 최근 실행 2시간 전' },
    { id: 2, name: '견적서 수식 오류 검출',      tags: ['A'],      meta: '대화형 트리거 · 수동 실행' },
    { id: 3, name: '계약서 수신 자동 분석',      tags: ['B', 'A'], meta: 'contract@office-ax.com 수신 시 · 대화 보정' },
    { id: 4, name: '주간 보고서 어투 변환',      tags: ['C', 'A'], meta: '매주 월 08:00 · RAG 적용' },
    { id: 5, name: '청구서 자동 발송',           tags: ['B', 'C'], meta: '수신 즉시 + 매월 25일' },
    { id: 6, name: '개인정보 자동 마스킹',       tags: ['A'],      meta: '대화형 트리거' },
  ]
}

export async function getPipelineById(id) {
  const list = await getPipelines()
  return list.find(p => p.id === Number(id)) ?? null
}

export async function getEmailInbox() {
  return [
    { from: '세무회계 김',  subject: '2025년 8월 청약 접수증 송부', file: '청약신청서 접수증.pdf',  time: '오전 02:17', status: '분석완료' },
    { from: 'ERP 자동발송', subject: '월간 견적 리포트',            file: '견적서_2508.xlsx',       time: '어제 18:40', status: '보정완료' },
    { from: '법무팀',       subject: '계약서 검토 요청',            file: '표준계약서_v3.hwp',      time: '어제 14:02', status: '검토중'   },
    { from: '고객지원',     subject: '민원 처리 결과 통보',         file: '민원결과.pdf',           time: '08-09',      status: '마스킹완료' },
    { from: '구매팀',       subject: '발주서 재검토 요청',          file: '발주서_0808.xlsx',       time: '08-08',      status: '검토중'   },
    { from: '인사팀',       subject: '재직증명서 발급',             file: '재직증명서.pdf',         time: '08-07',      status: '보정완료' },
  ]
}

export async function getRagAssets() {
  return {
    tones: [
      { id: 't1', name: '하람_보고서_스타일', active: true,  files: [{ name: '하람_2024_상반기보고서.docx', meta: 'docx · 248 KB' }, { name: '하람_월간보고_3월.docx', meta: 'docx · 192 KB' }, { name: '하람_결산보고.hwp', meta: 'hwp · 164 KB' }] },
      { id: 't2', name: '팀_공문_어투',      active: false, files: [{ name: '팀_대외공문_샘플.hwp', meta: 'hwp · 116 KB' }, { name: '팀_내부공지_양식.docx', meta: 'docx · 88 KB' }] },
    ],
    forms: [
      { id: 'f1', name: '회사_기획서_양식',  active: true,  files: [{ name: '신규사업_기획서.docx', meta: 'docx · 320 KB' }, { name: '제품기획_표준양식.docx', meta: 'docx · 274 KB' }, { name: '기획서_표지템플릿.pptx', meta: 'pptx · 410 KB' }] },
      { id: 'f2', name: '표준_계약서_양식',  active: false, files: [{ name: '용역계약서_표준.hwp', meta: 'hwp · 204 KB' }, { name: '비밀유지계약서.hwp', meta: 'hwp · 132 KB' }] },
    ],
  }
}
