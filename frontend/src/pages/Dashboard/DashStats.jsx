import { useEffect, useState } from 'react'
import { Ic } from '../../components/Ic'
import { getDashboardStats } from '../../api/client'

/** 도넛 차트 SVG */
function Donut({ pct }) {
  const r   = 26
  const c   = 2 * Math.PI * r
  const off = c * (1 - pct / 100)
  return (
    <div className="relative w-20 h-20 shrink-0">
      <svg className="w-20 h-20 -rotate-90" viewBox="0 0 64 64">
        <circle cx={32} cy={32} r={r} fill="none" strokeWidth={7} className="stroke-zinc-100 dark:stroke-zinc-800" />
        <circle cx={32} cy={32} r={r} fill="none" strokeWidth={7} strokeLinecap="round"
          className="stroke-blue-600"
          strokeDasharray={c}
          strokeDashoffset={off}
        />
      </svg>
      <div className="absolute inset-0 grid place-items-center">
        <span className="text-sm font-bold text-zinc-700 dark:text-zinc-200">{pct}%</span>
      </div>
    </div>
  )
}

/** 공통 통계 카드 */
function StatCard({ children }) {
  return (
    <div className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-6 shadow-sm">
      {children}
    </div>
  )
}

function CardHead({ icon, label }) {
  return (
    <div className="flex items-center gap-2 text-zinc-500 dark:text-zinc-400 text-sm mb-3">
      <Ic name={icon} />
      {label}
    </div>
  )
}

/**
 * 대시보드 상단 3개 통계 카드 (토큰 사용량 / 예상 비용 / 자동 처리 건수).
 * /dashboard/stats/ 응답(UsageEvent 실집계) 필드를 그대로 사용한다.
 */
export function DashStats() {
  const [stats, setStats] = useState(null)

  useEffect(() => {
    getDashboardStats().then(setStats)
  }, [])

  if (!stats) return null

  const {
    ai_calls,
    processed_documents,
    generated_revisions,
    failed_jobs,
    input_tokens,
    output_tokens,
    total_tokens,
    estimated_cost,
    monthly_token_limit,
    monthly_cost_limit,
    token_usage_percent,
    cost_usage_percent,
  } = stats

  return (
    <div className="grid grid-cols-3 gap-4 mb-6">
      {/* 토큰 사용량 */}
      <StatCard>
        <CardHead icon="coins" label="이번 달 토큰 사용량" />
        <div className="flex items-end gap-4">
          <Donut pct={token_usage_percent} />
          <div>
            <div className="text-[36px] leading-none font-bold tracking-tight text-zinc-800 dark:text-zinc-100">
              {total_tokens.toLocaleString()}
            </div>
            <div className="text-[18px] text-zinc-400 mt-1 font-medium">/ {monthly_token_limit.toLocaleString()} 토큰 (이번 달 한도)</div>
            <div className="text-xs text-zinc-500 dark:text-zinc-400 mt-2">
              입력 {input_tokens.toLocaleString()} · 출력 {output_tokens.toLocaleString()}
            </div>
          </div>
        </div>
      </StatCard>

      {/* 예상 비용 */}
      <StatCard>
        <CardHead icon="wallet" label="이번 달 예상 사용량" />
        <div className="text-[36px] leading-none font-bold tracking-tight text-zinc-800 dark:text-zinc-100">
          ₩ {estimated_cost.toLocaleString()}
        </div>
        <div className="text-[18px] text-zinc-400 mt-1 font-medium">
          이번 달 한도 ₩ {monthly_cost_limit.toLocaleString()} · {cost_usage_percent}% 사용
        </div>
        <div className="mt-3 h-1.5 rounded-full bg-zinc-100 dark:bg-zinc-800 overflow-hidden">
          <div
            className="h-full bg-blue-600 rounded-full"
            style={{ width: `${cost_usage_percent}%` }}
          />
        </div>
      </StatCard>

      {/* 자동 처리 건수 */}
      <StatCard>
        <CardHead icon="zap" label="이번 달 자동 처리" />
        <div className="text-[36px] leading-none font-bold tracking-tight text-zinc-800 dark:text-zinc-100">
          {ai_calls.toLocaleString()} 건
        </div>
        <div className="text-[18px] text-zinc-400 mt-1 font-medium">
          문서 분석 {processed_documents.toLocaleString()} · 수정본 생성 {generated_revisions.toLocaleString()} · 실패 {failed_jobs.toLocaleString()}
        </div>
      </StatCard>
    </div>
  )
}
