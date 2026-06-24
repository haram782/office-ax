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
    <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-5">
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
 * 대시보드 상단 3개 통계 카드 (토큰 / 잔고 / 처리 건수).
 */
export function DashStats() {
  const [stats, setStats] = useState(null)

  useEffect(() => {
    getDashboardStats().then(setStats)
  }, [])

  if (!stats) return null

  const { tokens, balance, processed } = stats

  return (
    <div className="grid grid-cols-3 gap-4 mb-6">
      {/* 토큰 잔여량 */}
      <StatCard>
        <CardHead icon="coins" label="잔여 토큰량" />
        <div className="flex items-end gap-4">
          <Donut pct={tokens.percent} />
          <div>
            <div className="text-2xl font-bold text-zinc-800 dark:text-zinc-100">
              {tokens.used.toLocaleString()}
            </div>
            <div className="text-xs text-zinc-400 mt-1">/ {tokens.total.toLocaleString()} 토큰</div>
            <div className="text-xs text-emerald-600 dark:text-emerald-400 mt-2">예상 소진 D-{tokens.daysLeft}</div>
          </div>
        </div>
      </StatCard>

      {/* 결제 잔고 */}
      <StatCard>
        <CardHead icon="wallet" label="결제 잔고 / 예치금" />
        <div className="text-2xl font-bold text-zinc-800 dark:text-zinc-100">
          ₩ {balance.remaining.toLocaleString()}
        </div>
        <div className="text-xs text-zinc-400 mt-1">
          예치금 ₩ {balance.total.toLocaleString()} · 이번 달 사용 ₩ {balance.used.toLocaleString()}
        </div>
        <div className="mt-3 h-1.5 rounded-full bg-zinc-100 dark:bg-zinc-800 overflow-hidden">
          <div
            className="h-full bg-blue-600 rounded-full"
            style={{ width: `${Math.round(balance.remaining / balance.total * 100)}%` }}
          />
        </div>
        <button className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium px-3 py-1.5">
          <Ic name="plus" className="w-3.5 h-3.5" />
          충전하기
        </button>
      </StatCard>

      {/* 자동 처리 건수 */}
      <StatCard>
        <CardHead icon="zap" label="이번 달 자동 처리" />
        <div className="text-2xl font-bold text-zinc-800 dark:text-zinc-100">
          {processed.count.toLocaleString()} 건
        </div>
        <div className="text-xs text-zinc-400 mt-1">
          오류 검출 {processed.errors.toLocaleString()} · 자동 보정 {processed.corrected.toLocaleString()}
        </div>
        {/* 바 차트 */}
        <div className="flex gap-1.5 mt-4 items-end h-10">
          {processed.chart.map((v, i) => (
            <div
              key={i}
              className="flex-1 rounded-sm bg-blue-500/70 dark:bg-blue-400/60"
              style={{ height: `${v}%` }}
            />
          ))}
        </div>
      </StatCard>
    </div>
  )
}
