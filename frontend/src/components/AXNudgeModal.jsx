import { useState, useEffect, useRef } from 'react'
import { activateWorkflow } from '../api/client'

const PHONE_REGEX = /^010\d{8}$/

export function AXNudgeModal({ workflow, onClose, onActivated }) {
  const [phone, setPhone] = useState('')
  const [phoneError, setPhoneError] = useState('')
  const [loading, setLoading] = useState(false)
  const [apiError, setApiError] = useState('')
  const phoneInputRef = useRef(null)

  // 모달이 열리면 전화번호 입력란에 포커스
  useEffect(() => {
    const timer = setTimeout(() => phoneInputRef.current?.focus(), 100)
    return () => clearTimeout(timer)
  }, [])

  // ESC 키로 닫기
  useEffect(() => {
    const onKeyDown = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  const handlePhoneChange = (e) => {
    const digits = e.target.value.replace(/\D/g, '').slice(0, 11)
    setPhone(digits)
    setPhoneError('')
    setApiError('')
  }

  const validatePhone = () => {
    if (!phone) { setPhoneError('휴대폰 번호를 입력해 주세요.'); return false }
    if (!PHONE_REGEX.test(phone)) { setPhoneError('올바른 번호 형식: 01012345678'); return false }
    return true
  }

  const handleActivate = async () => {
    if (!validatePhone()) return
    setLoading(true)
    setApiError('')
    try {
      const res = await activateWorkflow(workflow.id, phone)
      onActivated(res.inbound_email)
    } catch (err) {
      setApiError(err?.response?.data?.error ?? '활성화에 실패했습니다. 다시 시도해 주세요.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="nudge-modal-title"
    >
      {/* 백드롭 */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* 모달 패널 */}
      <div className="relative w-full sm:max-w-md bg-white rounded-t-3xl sm:rounded-3xl shadow-2xl overflow-hidden animate-fade-in-scale">

        {/* ── 헤더 (카카오 옐로우) ── */}
        <div className="bg-[#FEE500] px-6 pt-7 pb-5 relative">
          <button
            onClick={onClose}
            className="absolute top-4 right-4 w-8 h-8 rounded-full bg-black/10 hover:bg-black/20 flex items-center justify-center transition-colors"
            aria-label="닫기"
          >
            <span className="text-sm font-bold text-gray-700">✕</span>
          </button>

          <div className="text-4xl mb-3">💬</div>
          <h2 id="nudge-modal-title" className="text-xl font-bold text-gray-900 leading-snug">
            매번 올리기 번거로우시죠?
          </h2>
          <p className="text-sm text-gray-700 mt-1 font-medium">
            카카오톡으로 자동 분석 리포트 받아보기
          </p>
        </div>

        {/* ── 본문 ── */}
        <div className="px-6 py-5 space-y-4">

          {/* 안내 설명 */}
          <p className="text-sm text-gray-600 leading-relaxed">
            이 파일 유형을 <strong className="text-gray-800">매주 반복 업로드</strong>하시는 패턴이 감지되었습니다.
            아래 이메일로 파일을 첨부해 보내면, AI가 자동으로 분석 후 카카오톡으로 전송해 드립니다.
          </p>

          {/* 수신 이메일 표시 */}
          <div className="bg-gray-50 border border-gray-100 rounded-xl px-4 py-3">
            <p className="text-xs font-semibold text-gray-400 mb-1.5">나만의 자동 수신 이메일</p>
            <div className="flex items-center gap-2">
              <span className="text-sm font-mono font-semibold text-blue-600 break-all">
                {workflow.inbound_email ?? '활성화 후 발급됩니다'}
              </span>
              {workflow.inbound_email && (
                <CopyButton text={workflow.inbound_email} />
              )}
            </div>
            <p className="text-xs text-gray-400 mt-1.5">
              이 주소로 Excel·PDF 첨부 이메일을 보내면 자동 분석이 시작됩니다
            </p>
          </div>

          {/* 전화번호 입력 */}
          <div>
            <label
              htmlFor="phone-input"
              className="block text-xs font-semibold text-gray-500 mb-1.5"
            >
              카카오톡 수신 휴대폰 번호
            </label>
            <input
              id="phone-input"
              ref={phoneInputRef}
              type="tel"
              inputMode="numeric"
              value={phone}
              onChange={handlePhoneChange}
              onKeyDown={(e) => e.key === 'Enter' && handleActivate()}
              placeholder="01012345678 (하이픈 없이)"
              maxLength={11}
              disabled={loading}
              className={[
                'w-full rounded-xl border px-4 py-2.5 text-sm outline-none transition-all',
                'disabled:opacity-60 disabled:cursor-not-allowed',
                phoneError
                  ? 'border-red-400 bg-red-50 focus:ring-2 focus:ring-red-100'
                  : 'border-gray-200 bg-white focus:border-blue-400 focus:ring-2 focus:ring-blue-100',
              ].join(' ')}
            />
            {phoneError && (
              <p className="text-xs text-red-500 mt-1">{phoneError}</p>
            )}
          </div>

          {/* API 오류 */}
          {apiError && (
            <p className="text-xs text-red-600 bg-red-50 border border-red-100 rounded-lg px-3 py-2">
              {apiError}
            </p>
          )}

          {/* 활성화 버튼 */}
          <button
            onClick={handleActivate}
            disabled={loading}
            className={[
              'w-full py-3 rounded-xl font-semibold text-sm transition-all',
              'bg-[#FEE500] text-gray-900 hover:bg-yellow-400 active:scale-[0.98]',
              'disabled:opacity-60 disabled:cursor-not-allowed disabled:active:scale-100',
            ].join(' ')}
          >
            {loading
              ? <span className="flex items-center justify-center gap-2">
                  <span className="h-4 w-4 rounded-full border-2 border-gray-400 border-t-gray-800 animate-spin" />
                  활성화 중...
                </span>
              : '🚀 카카오톡 자동화 활성화'}
          </button>

          <button
            onClick={onClose}
            className="w-full py-2 text-sm text-gray-400 hover:text-gray-600 transition-colors"
          >
            나중에 하기
          </button>
        </div>
      </div>
    </div>
  )
}

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async (e) => {
    e.stopPropagation()
    await navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <button
      onClick={handleCopy}
      title="복사"
      className="flex-shrink-0 text-xs text-gray-400 hover:text-gray-700 transition-colors"
    >
      {copied ? '✅' : '📋'}
    </button>
  )
}
