export function AnalysisCard({ result, filename, onReset }) {
  if (!result) return null

  const summaryLines = (result.summary ?? '').split('\n').filter(Boolean)
  const errors = result.errors ?? []
  const piiRedacted = result.pii_redacted ?? {}
  const totalMasked = Object.values(piiRedacted).reduce((a, b) => a + b, 0)
  const { input = 0, output = 0 } = result.tokens ?? {}
  const hasError = result._notification_error

  return (
    <div className="rounded-2xl border border-gray-200 bg-white shadow-sm overflow-hidden">

      {/* ── 헤더 ── */}
      <div className="flex items-start justify-between gap-4 px-6 py-4 bg-gradient-to-r from-blue-600 to-indigo-600">
        <div className="min-w-0">
          <p className="text-xs font-semibold text-blue-200 uppercase tracking-widest mb-0.5">
            AI 분석 완료
          </p>
          <p className="text-white font-semibold truncate" title={filename}>{filename}</p>
        </div>
        <button
          onClick={onReset}
          className="flex-shrink-0 text-blue-200 hover:text-white text-sm underline underline-offset-2 transition-colors mt-0.5"
        >
          새 파일 분석
        </button>
      </div>

      <div className="p-6 space-y-6">

        {/* ── 3줄 요약 ── */}
        <section>
          <SectionTitle icon="📋" label="3줄 요약" />
          <ol className="mt-3 space-y-2.5">
            {summaryLines.length > 0 ? summaryLines.map((line, i) => (
              <li key={i} className="flex gap-3 text-gray-700 text-sm leading-relaxed">
                <span className="flex-shrink-0 mt-0.5 w-5 h-5 rounded-full bg-blue-100 text-blue-600 text-xs font-bold flex items-center justify-center">
                  {i + 1}
                </span>
                {line}
              </li>
            )) : (
              <li className="text-sm text-gray-400">요약 내용이 없습니다.</li>
            )}
          </ol>
        </section>

        {/* ── 감지된 오류 ── */}
        <section>
          <SectionTitle
            icon="⚠️"
            label={errors.length > 0 ? `감지된 오류 (${errors.length}건)` : '오류 검출 결과'}
          />
          {errors.length > 0 ? (
            <ul className="mt-3 space-y-2">
              {errors.map((err, i) => (
                <li
                  key={i}
                  className="flex gap-2.5 text-sm text-red-700 bg-red-50 border border-red-100 rounded-xl px-4 py-2.5"
                >
                  <span className="flex-shrink-0 mt-0.5">•</span>
                  {err}
                </li>
              ))}
            </ul>
          ) : (
            <div className="mt-3 flex items-center gap-2.5 text-sm text-green-700 bg-green-50 border border-green-100 rounded-xl px-4 py-3">
              <span>✅</span>
              <span>감지된 오류가 없습니다.</span>
            </div>
          )}
        </section>

        {/* ── 메타 정보 ── */}
        <div className="pt-1 space-y-2">
          {totalMasked > 0 && (
            <MetaBadge icon="🔒" text={`개인정보 ${totalMasked}건 — AI 전송 전 자동 마스킹 처리됨`} />
          )}
          {hasError && (
            <MetaBadge
              icon="📵"
              text={`카카오톡 알림 발송 실패 (대시보드에서 재시도 가능)`}
              variant="warn"
            />
          )}
          {(result.model_used || input + output > 0) && (
            <div className="flex flex-wrap gap-3 text-xs text-gray-400 pt-1">
              {result.model_used && <span>모델: {result.model_used}</span>}
              {input + output > 0 && (
                <span>토큰: {(input + output).toLocaleString()} (입력 {input.toLocaleString()} + 출력 {output.toLocaleString()})</span>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function SectionTitle({ icon, label }) {
  return (
    <h3 className="flex items-center gap-1.5 text-xs font-semibold text-gray-400 uppercase tracking-wider">
      <span>{icon}</span>
      {label}
    </h3>
  )
}

function MetaBadge({ icon, text, variant = 'default' }) {
  const colors = {
    default: 'bg-gray-50 text-gray-500 border-gray-100',
    warn: 'bg-orange-50 text-orange-600 border-orange-100',
  }
  return (
    <div className={`flex items-center gap-2 text-xs rounded-xl border px-4 py-2.5 ${colors[variant]}`}>
      <span>{icon}</span>
      <span>{text}</span>
    </div>
  )
}
